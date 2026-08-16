# Graph schema reference

Human-facing catalog of every label, relationship type, property, and
enum value in the Neo4j graph this pipeline loads. This file must agree
with `cypher/schema.cypher`, `cypher/validation.cypher`, `cypher/derive.cypher`,
and `queries/*.cypher` on every detail — if you change one, check the
others (design's "Shared resources" discipline).

Full design rationale lives in
[`docs/specs/dk-results-scraper/design.md`](../specs/dk-results-scraper/design.md)
(Decisions 1-3). This file is the quick-reference version.

## Shape

```
(:Club)-[:HAS_TEAM]->(:Team)
(:Team)-[:PLAYED_IN {side, goalsFor, goalsAgainst, outcome, points,
                     penaltyGoalsFor, penaltyGoalsAgainst}]->(:Match)
(:Match)-[:IN_STAGE]->(:Stage)-[:IN_SEASON]->(:Season)<-[:HAS_SEASON]-(:Competition)
(:Match)-[:PLAYED_AT]->(:Venue)
(:Team)-[:PARTICIPATED_IN {rank, played, won, drawn, lost,
                           goalsFor, goalsAgainst, goalDifference, points}]->(:Stage)
(:Team)-[:PLAYED_AGAINST {matchCount}]->(:Team)     # derived, rebuilt each `dkfr derive`
```

7 node labels, 7 stored relationship types, 1 derived relationship type.

## Labels

| Label | Business key | Properties |
|---|---|---|
| `Club` | `clubId` (slug, default from squad-ordinal-stripped team name; overridable via `manifest/clubs.yaml`) | `name` |
| `Team` | `teamId` (`dbu:<numericTeamId>`, or `name:<slug>\|<bracket>` fallback — see Decision 3) | `name`, `bracket`, `gender`, `ageBracket`, `squadIndex`, `dbuTeamId`, `sourceNames[]` |
| `Match` | `matchKey` (`<puljeId>:<matchNumber>`, or a deterministic date/team fallback) | `matchNumber`, `date`, `kickoffAt` (UTC instant), `kickoffTimeLocal`, `status`, `totalGoals`, `goalMargin`, `hasPenalties`, `puljeId`, `competitionId`, `phase`, `tier`, `bracket`, `gender`, `ageBracket`, `season`, `sourceUrl`, `fetchedAt`, `scraperVersion` |
| `Stage` | `puljeId` | `name` (currently always null — see "Known limitations" below), `phase`, `groupLabel`, `competitionId`, `season`, `tier`, `bracket`, `administrator`, `pointsCarryOver`, `teamCount`, `matchCount`, `sourceUrl`, `fetchedAt` |
| `Season` | `seasonId` (`<competitionId>:2025-26`) | `label` (`"2025/26"`), `seasonCode` (`"2026"`) |
| `Competition` | `competitionId` (manifest slug, e.g. `3f-superliga`) | `name`, `bracket`, `gender`, `ageBracket`, `tier`, `administrator` |
| `Venue` | `venueKey` (slug of venue name) | `name` |

**There are deliberately no `homeGoals`/`awayGoals` properties on `Match`.**
Per-side goals live only on `PLAYED_IN` (Decision 2) — read them via
`(t:Team)-[p:PLAYED_IN {side:'HOME'}]->(m)` / `p.goalsFor`, not `m.homeGoals`.

## Relationship types

| Type | Direction | Properties | Notes |
|---|---|---|---|
| `HAS_TEAM` | `(Club)->(Team)` | — | |
| `PLAYED_IN` | `(Team)->(Match)` | `side` (`HOME`/`AWAY`), `goalsFor`, `goalsAgainst`, `outcome` (`WIN`/`DRAW`/`LOSS`/`UNKNOWN`), `points` (3/1/0), `penaltyGoalsFor`, `penaltyGoalsAgainst` | Exactly 2 per Match — one HOME, one AWAY, from distinct teams (checked, see below). |
| `IN_STAGE` | `(Match)->(Stage)` | — | Exactly 1 per Match (checked). |
| `IN_SEASON` | `(Stage)->(Season)` | — | |
| `HAS_SEASON` | `(Competition)->(Season)` | — | |
| `PLAYED_AT` | `(Match)->(Venue)` | — | Only present when the match had a scraped venue name. |
| `PARTICIPATED_IN` | `(Team)->(Stage)` | `rank`, `played`, `won`, `drawn`, `lost`, `goalsFor`, `goalsAgainst`, `goalDifference`, `points` | The scraped `stillingFuld` standings row — the validation oracle for U10/AC8. |
| `PLAYED_AGAINST` (derived) | `(Team)->(Team)`, lower `teamId` -> higher `teamId` (string comparison), but always queried **undirected** | `matchCount` | Full drop-and-rebuild on every `dkfr derive` — see `cypher/derive.cypher`. |

## Enums (single source of truth: `src/dkfr/vocab.py`)

| Enum | Values |
|---|---|
| `Gender` | `MEN`, `WOMEN` |
| `AgeBracket` | `SENIOR`, `U19`, `U17`, `U16` |
| `Bracket` | `MEN_SENIOR`, `WOMEN_SENIOR`, `MEN_U19`, `MEN_U17`, `WOMEN_U19`, `WOMEN_U16` — mechanically derived from `(gender, ageBracket)`, never set independently |
| `Phase` | `GRUNDSPIL`, `MESTERSKABSSPIL`, `OPRYKNINGSSPIL`, `NEDRYKNINGSSPIL` (reserved, not observed in the real 2025/26 manifest — DBU uses `KVALIFIKATIONSSPIL` for the relegation-side playoff instead), `KVALIFIKATIONSSPIL`, `SINGLE`, `CUP` (reserved, unused — see spec N8) |
| `Administrator` | `DBU`, `DIVISIONSFORENINGEN` |
| `Side` | `HOME`, `AWAY` |
| `Outcome` | `WIN`, `DRAW`, `LOSS`, `UNKNOWN` (not-played / no goals) |
| `MatchStatus` | `PLAYED`, `NOT_PLAYED`, `POSTPONED`, `ABANDONED`, `ANNULLED`, `WALKOVER`, `UNKNOWN` |

**`tier` is an integer scoped *within* `bracket`, never comparable across
brackets.** "1. Division" (`MEN_SENIOR`, tier 2) and "U19 Drenge Ligaen"
(`MEN_U19`, tier 1) are not on the same scale — every query that filters
or orders on `tier` must also filter on `bracket` (see `queries/u11-biggest-wins.cypher`
for the correct pattern). This is a deliberate design tradeoff (Decision 1),
not an oversight.

## Post-load invariants (`cypher/validation.cypher`, run by `dkfr validate`)

Neo4j Community Edition can only enforce uniqueness (spec C10) — these are
checked after every load, not enforced by the schema itself:

1. `match_has_exactly_two_sides` — every `Match` has exactly one `HOME` and
   one `AWAY` `PLAYED_IN` edge, from two distinct teams.
2. `played_in_goals_are_symmetric` — a match's HOME `goalsFor` equals its
   AWAY `goalsAgainst`, and vice versa.
3. `played_in_outcome_and_points_agree_with_goals` — `outcome`/`points`
   are internally consistent with `goalsFor`/`goalsAgainst`.
4. `every_team_has_exactly_one_club` — every `Team` has exactly one
   `HAS_TEAM` edge.
5. `every_match_has_exactly_one_stage` — every `Match` has exactly one
   `IN_STAGE` edge.
6. `match_scalars_agree_with_stage` — `Match`'s denormalized scalar copies
   (`puljeId`, `phase`, `tier`, `bracket`, `season`, `competitionId`) equal
   their source `Stage`'s values (Decision 1's checked drift guard).
7. `no_orphan_team_nodes` — every `Team` has at least one `PLAYED_IN` or
   `PARTICIPATED_IN` edge.
8. `no_orphan_venue_nodes` — every `Venue` has at least one `PLAYED_AT`
   edge.
9. `every_stage_has_a_competition` — every `Stage.competitionId` resolves
   to a real `Competition` node.

## Known limitations

- **`Stage.name` is always `null`.** The parsers extract match/standings/
  roster data from each pulje's tables but don't currently retain the
  page's own `<h2>` title text as a stored field (it's used transiently
  during `dkfr manifest verify`'s title-matching check, then discarded).
  Not load-bearing for any of U1-U11 or AC1-AC21 — `Stage.groupLabel` plus
  `Competition.name` plus `Stage.phase` together identify a pulje
  human-readably. Flagged here rather than silently left unexplained.
- **`PLAYED_IN.points` uses a plain 3/1/0 W/D/L formula and does not model
  DBU's apparent penalty-shootout bonus-point scheme** on at least one
  bracket (U19 Drenge Ligaen — see `docs/specs/dk-results-scraper/discovery-notes.md`'s
  T14 addendum and `data/reports/standings-reconciliation.json`). This
  affects `points` only, never `goalsFor`/`goalsAgainst`/`outcome`/W-D-L
  counts, and is visible/explained in the standings reconciliation report,
  not silently wrong.
- **`pointsCarryOver: true` puljer are not comparable to their own matches
  on ANY standings column**, not just points — see the T14 addendum in
  discovery-notes.md. `dkfr.load.reconcile` skips these rather than
  reporting a misleading failure.
