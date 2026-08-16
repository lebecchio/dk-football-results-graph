# Design: Danish Football Results Scraper → Neo4j (2025/26)

**Status:** For developer implementation
**Author:** architect
**Date:** 2026-08-16
**Spec:** `/Users/teislebeck/dk-football-results-graph/docs/specs/dk-results-scraper/spec.md`
**Prior art evaluated:** `/Users/teislebeck/football-graph-schema/docs/schema/model.md`

---

## Design summary

### Shape of the system

Four strictly separated stages, each independently runnable and each writing a durable artefact the next stage reads. This is the spec's R3.2 layering made structural:

```
manifest/puljer.yaml
        │
        ▼
 [1] FETCH ──────────► data/cache/pulje/<puljeId>/<view>.html + .meta.json
        │                (robots-checked, ≥2s serial, honest UA, retried)
        ▼
 [2] PARSE + NORMALIZE ► data/normalized/{matches.jsonl, puljer.json,
        │                 teams.json, clubs.json, venues.json}
        │                + data/reports/{parse-issues,unresolved-names}.json
        │                (zero network: reads cache only)
        ▼
 [3] LOAD ─────────────► Neo4j (local Docker), MERGE-idempotent
        │                then DERIVE (PLAYED_AGAINST projection)
        ▼
 [4] VALIDATE ─────────► data/reports/{validation,standings-reconciliation}.json
```

The hard boundary is between [1] and [2]: **the parser never touches the network**, so parser iteration costs zero requests (R2.6, the single most important politeness measure). The second hard boundary is between [2] and [3]: `matches.jsonl` is self-contained and complete enough to rebuild the whole graph with the scraper deleted (R3.1/G2), which is what makes schema iteration cheap.

### Tech stack, and why

| Choice | Justification |
|---|---|
| **Python 3.12+** | Best-in-class HTML parsing ecosystem, the official first-party Neo4j driver, and a solo-dev-friendly toolchain. The workload is ~210 HTTP requests and ~13k records — performance is a non-issue, so ergonomics and library maturity decide. |
| **uv** (env + deps + lockfile) | Single-binary, fast, reproducible. `uv run dkfr ...` with no venv ceremony. |
| **httpx** (sync client) | Explicit timeouts, clean header/UA control, good testing story via `pytest-httpx`. Sync only — R2.3 mandates serial requests, so async buys nothing and risks accidental concurrency. |
| **BeautifulSoup4 + lxml** | Forgiving of real-world markup. Deliberately **not** `pandas.read_html`: it discards `<a href>` values (which likely carry the authoritative team and match IDs — see Task 3) and gives no per-cell error handling, which R2.9/AC11 require. |
| **pydantic v2 + pydantic-settings** | The normalized JSON schema *is* a set of pydantic models — one source of truth for the [2]→[3] contract, and it gives AC3's field-completeness assertion for free. Settings handle the `.env`. |
| **PyYAML** | Manifest and alias files. YAML over JSON specifically because these are **hand-curated and need comments** (provenance note per pulje ID); JSON forbids comments. |
| **typer + rich** | One `dkfr` CLI with a subcommand per stage (AC20's "run each stage independently"), readable report output. |
| **neo4j** (official driver, `>=5.26,<6`) | Bolt, works against Docker or Aura identically (R3.4). |
| **rapidfuzz** | Fuzzy *suggestions* for the unresolved-names report only — never auto-resolution (C9/AC10). |
| **pytest + ruff** | Standard. |
| **Docker Compose, `neo4j:5.26-community`** | 5.26 LTS rather than the calver line: longest support window, widest doc/driver compatibility, and relationship-property range indexes (load-bearing for Decision 2) have existed since 5.0. No APOC dependency anywhere — every query is plain Cypher. |

Nothing here needs a paid tier, an account, or a network dependency beyond dbu.dk itself (C14).

---

## Decision 1 — Modelling phase and tier

**Problem (spec F2, R1, U9, AC19, Q2):** a Superliga team's Grundspil and Mesterskabsspil matches must be distinguishable, but the team must remain **one node** — the failure mode is keying team identity off `puljeId` and ending up with two "FC København" nodes.

**Decision: make the pulje a first-class `Stage` node; key `Team` independently of any pulje; encode tier as `(bracket, tier)`.**

```
(:Competition)-[:HAS_SEASON]->(:Season)<-[:IN_SEASON]-(:Stage)<-[:IN_STAGE]-(:Match)
```

- **`Stage` == exactly one pulje.** `stage.puljeId` is the key. It carries `phase`, `groupLabel`, `name` (the scraped pulje title), `administrator`, `pointsCarryOver`, and provenance. This is the natural unit — the spec's finding #1 says the pulje is the unit of scraping, and it turns out to be the right unit of modelling too.
- **Team identity never touches `puljeId`.** A team that plays Grundspil then Mesterskabsspil is one `Team` node with `PLAYED_IN` relationships to matches in two different Stages. U9 becomes a single one-hop-plus-one query, and AC19 falls out of grouping by `s.phase`.
- **`Stage` also anchors the standings.** `(:Team)-[:PARTICIPATED_IN {rank, played, won, drawn, lost, goalsFor, goalsAgainst, points}]->(:Stage)`, populated from the scraped `stillingFuld`. This gives the validation oracle (AC8/U10) a home *inside the graph*, so reconciliation is a Cypher query rather than a bespoke Python comparison.

**Tier encoding — answering Q2 with option (b), sharpened.** `bracket` is the discriminator and it is **mechanically derived from `(gender, ageBracket)`**, so there is no third vocabulary to keep in sync:

| `bracket` | `gender` | `ageBracket` | Competitions in scope (tier) |
|---|---|---|---|
| `MEN_SENIOR` | `MEN` | `SENIOR` | Superliga (1), 1. Div (2), 2. Div (3), 3. Div (4), Danmarksserien (5) |
| `WOMEN_SENIOR` | `WOMEN` | `SENIOR` | A-Liga (1), B-Liga (2) |
| `MEN_U19` | `MEN` | `U19` | U19 Drenge Ligaen (1) |
| `MEN_U17` | `MEN` | `U17` | U17 Drenge Ligaen (1) |
| `WOMEN_U19` | `WOMEN` | `U19` | U19 Piger (1) |
| `WOMEN_U16` | `WOMEN` | `U16` | U16 Piger (1) |

`tier` is an integer **scoped within `bracket`** and is meaningless when compared across brackets. This is the one sharp edge of the decision, and the mitigation is documented convention: **every query that filters or orders on `tier` must also filter on `bracket`.** The alternative — a single global tier scale — would require inventing a defensible ordering between "1. Division" and "U19 Drenge Ligaen", which does not exist.

`tier` lives on `Competition` (a competition's tier is a season-stable fact for 2025/26). If a future season re-tiers a competition, `tier` moves to `Season` — additive, no rework.

**`phase` enum:** `GRUNDSPIL`, `MESTERSKABSSPIL`, `OPRYKNINGSSPIL`, `NEDRYKNINGSSPIL`, `KVALIFIKATIONSSPIL`, `SINGLE`, and **`CUP` reserved but unused** — so Q4 (cup competitions) can be absorbed later by adding manifest rows only, with zero schema change.

**Denormalization onto `Match` — a deliberate deviation from the prior art.** `Match` carries scalar copies of `season`, `competitionId`, `phase`, `tier`, `bracket`, `gender`, `ageBracket`, `puljeId`. The prior-art model argued against storing a redundant `Match→Competition` *edge*, and that argument is correct and respected here (no such edge exists). Scalar copies are a different tradeoff:

- They create no ambiguous multi-path traversal — there is exactly one way to walk from a Match to its Competition.
- They are written by a **single loader from a single JSON record**, so drift is a loader bug, not a data-integrity hazard, and it is caught by a post-load validation query (`Match` scalars must equal their `Stage`/`Competition` values).
- They buy index-backed filtering on the hot paths (U1, U3, U11) with no extra hops.

**`Stage` is the source of truth; `Match` scalars are load-time derived copies.** That rule is checked, not just documented.

---

## Decision 2 — Per-side match facts live on the relationship

**Decision: Option B — a single `PLAYED_IN` relationship type, `side` as a property, per-side facts as relationship properties.** Same conclusion as the prior art, reached independently and, for this project, on stronger grounds.

```cypher
(:Team)-[:PLAYED_IN {side, goalsFor, goalsAgainst, outcome, points,
                     penaltyGoalsFor, penaltyGoalsAgainst}]->(:Match)
```

Evaluation against **this** project's requirements:

| Option | Verdict against AC17 |
|---|---|
| **A.** `HOME_IN`/`AWAY_IN` types + `home_*`/`away_*` props on `Match` | **Disqualified.** AC17 explicitly forbids `UNION` and `CASE`-on-relationship-type, which is exactly what A forces at every hop. Not a judgement call — the spec rules it out. |
| **B.** Single `PLAYED_IN`, `side` + stats as rel properties | **Chosen.** U1 and U2 are one pattern each, no branching. |
| **C.** Reified `TeamMatch` node | Satisfies AC17 but doubles physical hops on U5/U6 (the multi-hop queries) for zero benefit. |

Two points where this project differs from the prior art, both strengthening B:

1. **There are no rich per-side stats here.** N4 keeps v1 match-level: the entire per-side payload is goals, penalties, and two derived fields. The strongest argument for reification (C) — "stats are large, variable, or independently queried" — is absent by construction. **Drop the prior art's `extraStats` JSON escape hatch entirely**: it existed because no real sample of the stats JSON was available. Here the source pages are known and sampled. Adding it would be speculative complexity.
2. **The denormalized convenience fields are safe here.** The prior art flagged `goalsAgainst`/`outcome` as drift risks under unknown ingestion. In this project both sides of a match are written in one transaction from one JSON record by one loader, and a validation query asserts `p.goalsFor = q.goalsAgainst` and outcome consistency across every pair. **Keep them, and add `points` (3/1/0)** — that turns U10 (derived standings) into a pure `sum(p.points)` aggregation over `PLAYED_IN` with no opponent lookup at all, which is a large simplification of the project's validation story.

**Side-neutral facts stay on `Match`** — including two derived scalars that are genuinely side-neutral and make U11 an index-backed node scan rather than a traversal:

- `totalGoals` (indexed) — "highest-scoring matches"
- `goalMargin` (absolute difference, indexed) — "biggest wins"

There are deliberately **no** `homeGoals`/`awayGoals` properties on `Match`. That would be Option A leaking back in, and it would give two representations of the same fact.

---

## Decision 3 — Team identity resolution across puljer

**Decision: a layered resolver with a preferred key and a designed fallback, gated on an empirical check (Task 3).** The design is written so that either answer to Q6 works, and the branch is a one-line configuration choice, not a redesign.

### Identity key

`Team.teamId` is assigned by the first rule that applies:

1. **`dbu:<numericTeamId>`** — if Task 3 confirms DBU's numeric team ID is stable across puljer. Fuzzy matching then becomes irrelevant for identity (it stays relevant only for club grouping).
2. **`name:<normalizedName>|<bracket>`** — the normalized display name, scoped to bracket.

Two invariants hold in both branches:

- **`puljeId` is never part of the team key.** This is the fragmentation failure mode the spec warns about, and it is structurally excluded.
- **`bracket` *is* part of the team key** (branch 2) or is at minimum validated against it (branch 1). "FC København" renders identically in the men's senior, U19, and U17 fixture tables — bracket is the only thing distinguishing three genuinely different competing entities, and U7/AC18 depend on that split existing.
- **Season is *not* part of the team key.** Team continuity across seasons is the desired behaviour for a future N3 phase.

### Where team IDs come from

Fetching `/resultater/pulje/<id>/holdoversigt` — a **third request per pulje** (~+70 requests, still a trivial crawl) — is worth doing unconditionally, regardless of the Q6 answer:

- If teamIds are cross-pulje stable, it hands us identity for free.
- If they are not, it still gives an **authoritative, exact roster of team display names for that pulje**, which anchors fixture-row name matching (fixture cells can truncate or abbreviate) and bounds the fuzzy-match candidate set to ~12 names instead of ~600.

Task 3 must also check whether `kampprogramFuld` fixture rows already hyperlink team cells to `/resultater/hold/<teamId>_<puljeId>/`. If so, `holdoversigt` becomes belt-and-braces and team IDs arrive with the fixtures.

### Resolution pipeline

```
raw cell text
  → normalize()      NFC, strip, collapse whitespace, strip stray punctuation,
                     casefold for the key only (display name preserved verbatim)
  → split squad ordinal   "AaB 2" / "B 93 (2)" → (base name, squadIndex=2)
  → alias lookup     manifest/aliases.yaml: rawName → canonical + optional clubId
  → pulje roster match (exact, against holdoversigt names)
  → dbuTeamId if available
  → UNRESOLVED  → data/reports/unresolved-names.json (with rapidfuzz suggestions)
```

**Auto-acceptance is exact-match only.** rapidfuzz produces ranked *suggestions written into the report for a human to promote into `aliases.yaml`* — it never resolves. This is the literal reading of AC10 ("not silently guessed") and of C9 ("do not expect a fully automatic solution").

### Club resolution — default rule plus a small exceptions file

Hand-curating ~400 clubs is unnecessary. DBU renders the same short club name across brackets ("FC København" in the U19 table too), so:

- **Default:** `clubId = slug(canonicalTeamName with squad ordinal stripped)`. This makes U7/AC18 work out of the box — FCK's senior, U19 and U17 teams all land under `fc-koebenhavn`.
- **Exceptions only:** `manifest/clubs.yaml` maps canonical team names to a different `clubId` and a display name, for cases where the rendered short name differs across brackets or is an initialism ("VRI", "Fuglebakken KFUM").

The unresolved-names report should additionally flag **club-grouping suspects**: canonical names that fuzzy-match an existing `clubId` above a threshold but were not merged. That surfaces "should these be one club?" for human decision without acting on it.

---

## Components / files affected

Greenfield — every path below is new. All paths absolute from the repo root `/Users/teislebeck/dk-football-results-graph`.

### Configuration and infrastructure

| Path | Purpose |
|---|---|
| `pyproject.toml` | uv project, deps, ruff + pytest config, `dkfr` console script, `__version__` as `scraperVersion`. |
| `docker-compose.yml` | `neo4j:5.26-community`, ports 7474/7687, named volumes, memory settings, no APOC. |
| `.env.example` | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `DBU_CONTACT_EMAIL`. |
| `.gitignore` | `data/`, `.env`, `.venv/` — **AC21**. |
| `README.md` | Per-stage run instructions, manifest format, C1/C2 constraints, explicit no-republication statement — **AC20**. |

### Manifest and curated data (checked in, human-editable)

| Path | Purpose |
|---|---|
| `manifest/puljer.yaml` | **R2.1.** Two top-level sections: `competitions:` (name, bracket, gender, ageBracket, tier, administrator — declared once) and `puljer:` (puljeId, competitionId ref, phase, groupLabel, pointsCarryOver, expectedTeams, expectedMatches, note). ~70 entries. |
| `manifest/aliases.yaml` | Raw team name → canonical name (+ optional clubId, dbuTeamId). **AC10.** |
| `manifest/clubs.yaml` | Canonical-name → clubId/display-name exceptions to the default slug rule. |

Manifest entry shape:

```yaml
competitions:
  3f-superliga:
    name: "3F Superliga"
    bracket: MEN_SENIOR
    gender: MEN
    ageBracket: SENIOR
    tier: 1
    administrator: DIVISIONSFORENINGEN
puljer:
  - puljeId: 473806
    competitionId: 3f-superliga
    phase: GRUNDSPIL
    groupLabel: null
    pointsCarryOver: false
    expectedTeams: 12
    expectedMatches: 132
    note: "confirmed from pulje title 2026-08-16"
```

### Source package `src/dkfr/`

| Module | Responsibility |
|---|---|
| `__init__.py` | `__version__` — the `scraperVersion` stamped on every record. A pinned constant, **not** `git describe` (a dirty tree would break AC7 byte-identity). |
| `vocab.py` | **Shared spine.** All enums: `Phase`, `Bracket`, `Gender`, `AgeBracket`, `Side`, `Outcome`, `MatchStatus`, `Administrator`. Imported by manifest, parser, records, loader, and referenced by the query docs. Single source of the vocabulary. |
| `config.py` | pydantic-settings. `DBU_CONTACT_EMAIL` has **no default** — the honest-UA requirement (R2.4) is structural, the tool refuses to run without it. |
| `cli.py` | typer app: `fetch`, `parse`, `load`, `derive`, `validate`, `query`, `manifest verify`, `names review`, `all`. |
| `manifest.py` | pydantic models for the manifest, loader, referential checks, and `verify` (fetches each pulje landing page, asserts the title matches declared competition/phase/season code — **AC1**). |
| `fetch/robots.py` | `urllib.robotparser` wrapper. Every URL checked before request; disallowed → raise, never skip silently. **AC5.** |
| `fetch/cache.py` | URL → `data/cache/pulje/<puljeId>/<view>.html` + `<view>.meta.json` (`{url, fetchedAt, status, elapsedMs, contentSha256, requestHeaders}`). Human-inspectable paths, hash fallback for unstructured URLs. |
| `fetch/client.py` | `Fetcher`: serial, ≥2.0s gate on **network** requests only (cache hits are free), retries (3× exponential 5/15/45s on 429/5xx/timeout, honours `Retry-After`), 404 on a manifest pulje is fatal (R2.7), path allow-list restricted to `/resultater/pulje/` (enforces R2.8 — no assets, ever), request log to `data/logs/requests-<runid>.jsonl` (**AC5/AC6** evidence). |
| `parse/tables.py` | Generic header-text-driven table extractor. Locates tables and columns by **Danish header text** (`Kampnr`, `Dato`, `Tid`, `Hjemme`, `Ude`, `Spillested`, `Resultat`), not by CSS class or nth-child — so cosmetic markup changes don't break it. Returns cell text *and* cell `<a href>`s. |
| `parse/values.py` | The tolerant scalar parsers. Highest-value unit-test surface. See below. |
| `parse/fixtures.py` | `kampprogramFuld` → raw match rows + issues. |
| `parse/standings.py` | `stillingFuld` → standings rows (K/V/U/T/Score/P). |
| `parse/teams.py` | `holdoversigt` → (dbuTeamId, displayName). |
| `parse/issues.py` | `ParseIssue{sourceUrl, rowIndex, rawRow, reason, severity}`. Every parser returns `(records, issues)`. **Nothing is ever silently dropped (R2.9/AC11).** |
| `normalize/names.py` | Unicode/whitespace normalization, squad-ordinal splitting, slug generation (Danish æ/ø/å → ae/oe/aa). |
| `normalize/resolver.py` | `TeamResolver` / `ClubResolver` per Decision 3, plus rapidfuzz suggestion generation. |
| `normalize/records.py` | **The [2]→[3] contract.** pydantic models: `MatchRecord`, `PuljeRecord`, `TeamRecord`, `ClubRecord`, `VenueRecord`, `StandingRow`. AC3 completeness is a model-level assertion. |
| `normalize/writer.py` | Deterministic writers: sorted keys, stable record ordering (`matches` by `(puljeId, date, matchNumber)`), `ensure_ascii=False`, LF endings, trailing newline. `fetchedAt` sourced from the **cache sidecar**, never from wall clock — this is what makes **AC7** achievable. |
| `load/driver.py` | Neo4j driver/session lifecycle, batching helper (`UNWIND $rows` at 500/batch, `execute_write`). |
| `load/schema.py` | Applies `cypher/schema.cypher`. **AC12.** |
| `load/loader.py` | Ordered idempotent MERGE load (R3.5). |
| `load/derive.py` | Rebuilds the `PLAYED_AGAINST` projection (full drop-and-rebuild = idempotent by construction). |
| `load/validate.py` | Runs `cypher/validation.cypher` assertions + JSON↔graph count reconciliation + standings reconciliation. Non-empty violation result → non-zero exit. **AC13/14/15/8.** |
| `queries/runner.py` | Loads a `.cypher` file from `queries/`, binds `--param` values, prints a table. Makes AC16's "checked-in queries" executable and testable. |

`parse/values.py` handles every C8 variation, each independently unit-testable:

- `parse_score` — `"2 - 2"`, `"4-2"`, `"2–2"` (en dash), `"2 : 2"`, empty, `"-"`.
- `parse_penalties` — `"Straffesparkskonkurrence 4 - 5"`. **Must scan both the result cell's full text and any trailing sibling cell** — the spec's verbatim sample is ambiguous about which; Task 3 resolves it, the parser handles both.
- `parse_danish_date` — `"lør.09-08 2025"` → `date(2025, 8, 9)`. Weekday map `man/tir/ons/tor/fre/lør/søn`. **Validate the parsed weekday against the computed date** — a free correctness check; a mismatch raises a parse warning rather than passing silently.
- `parse_time` + `to_instant` — local `HH:MM` combined with the date in `Europe/Copenhagen`. Store **both** `date` (local ISO date) and `kickoffAt` (UTC instant); the season spans a DST boundary, and storing only an instant makes "which matchday was this" fragile.
- `parse_status` — score present → `PLAYED`; empty → `NOT_PLAYED`; recognized Danish markers (`Udsat`, `Afbrudt`, `Annulleret`, `Ikke afviklet`, `Walkover`/`WO`) → `POSTPONED`/`ABANDONED`/`ANNULLED`/`WALKOVER`. **Any unrecognized non-empty result text → `UNKNOWN` plus an error-severity issue.** The exact marker vocabulary is a Task 3 output.

### Cypher artefacts

| Path | Purpose |
|---|---|
| `cypher/schema.cypher` | Uniqueness constraints + indexes, all `IF NOT EXISTS`. **AC12.** |
| `cypher/validation.cypher` | Named assertion queries, each returning violations (empty = pass). |
| `cypher/derive.cypher` | `PLAYED_AGAINST` rebuild. |
| `queries/u01-opponents.cypher` … `u11-biggest-wins.cypher` | **AC16.** One file per use case, with a header comment stating purpose, parameters, and expected shape. |
| `docs/schema/model.md` | Human-facing schema reference: label/relationship catalog, property tables, enum values, invariants. Mirrors the prior-art repo's documentation discipline. |

### Tests

| Path | Purpose |
|---|---|
| `tests/fixtures/html/*.html` | **Synthetic**, hand-authored table markup reproducing every observed structure and format variation — *not* saved DBU pages. See Risk 6. |
| `tests/test_values.py` | Table-driven, covering every C8 variant and every Task 3 finding. |
| `tests/test_tables.py`, `test_fixtures_parser.py`, `test_standings_parser.py` | Structure extraction. |
| `tests/test_resolver.py` | Cross-pulje identity: same team in Grundspil + Mesterskabsspil resolves to one `teamId`; same short name in senior + U19 resolves to two. |
| `tests/test_determinism.py` | Parse twice from a warm cache → byte-identical output. **AC7.** |
| `tests/test_fetch_politeness.py` | Robots refusal, ≥2s spacing, UA content, cache-hit issues zero requests. **AC5/AC6.** |
| `tests/test_load_idempotency.py` | Load a golden sample twice → identical counts. **AC14.** Requires a live Neo4j; marked and skippable. |
| `tests/golden/matches.sample.jsonl` | ~50 **synthetic** matches spanning brackets, phases, penalties, and not-played statuses. The parallel-workstream contract artefact. |

---

## Graph schema (reference)

```
(:Club)-[:HAS_TEAM]->(:Team)
(:Team)-[:PLAYED_IN {side, goalsFor, goalsAgainst, outcome, points,
                     penaltyGoalsFor, penaltyGoalsAgainst}]->(:Match)
(:Match)-[:IN_STAGE]->(:Stage)-[:IN_SEASON]->(:Season)<-[:HAS_SEASON]-(:Competition)
(:Match)-[:PLAYED_AT]->(:Venue)
(:Team)-[:PARTICIPATED_IN {rank, played, won, drawn, lost,
                           goalsFor, goalsAgainst, goalDifference, points}]->(:Stage)
(:Team)-[:PLAYED_AGAINST {matchCount}]-(:Team)     # derived, rebuilt each load
```

7 node labels, 6 stored relationship types, 1 derived.

| Label | Key | Notable properties |
|---|---|---|
| `Club` | `clubId` | `name` |
| `Team` | `teamId` | `name`, `bracket`, `gender`, `ageBracket`, `squadIndex`, `dbuTeamId`, `sourceNames[]` |
| `Match` | `matchKey` | `matchNumber`, `date`, `kickoffAt`, `kickoffTimeLocal`, `status`, `totalGoals`, `goalMargin`, `hasPenalties`, `puljeId`, `competitionId`, `phase`, `tier`, `bracket`, `gender`, `ageBracket`, `season`, `sourceUrl`, `fetchedAt`, `scraperVersion` |
| `Stage` | `puljeId` | `name`, `phase`, `groupLabel`, `competitionId`, `season`, `tier`, `bracket`, `administrator`, `pointsCarryOver`, `teamCount`, `matchCount`, `sourceUrl`, `fetchedAt` |
| `Season` | `seasonId` (`<competitionId>:2025-26`) | `label`, `seasonCode` (2026), `startDate`, `endDate` |
| `Competition` | `competitionId` | `name`, `bracket`, `gender`, `ageBracket`, `tier`, `administrator` |
| `Venue` | `venueKey` (normalized name) | `name` |

**`matchKey` = `f"{puljeId}:{matchNumber}"`** — the composite the spec recommends for Q5, safe whether or not `Kampnr` is globally unique. `matchNumber` is kept as its own indexed property so proven global uniqueness can be exploited later without a key migration. If `Kampnr` is absent (the U19 sample suggests it can be) the fallback is the deterministic `f"{puljeId}:{isoDate}:{homeTeamId}:{awayTeamId}"`; if fixture rows link to `/resultater/kamp/<matchId>_<puljeId>/`, that `matchId` is preferred over `Kampnr`. Task 3 decides.

**Indexes:** `Match.date`, `Match.totalGoals`, `Match.goalMargin`, `Match.bracket`, `Match.phase`, `Team.name`, `Club.name`, and relationship-property indexes on `PLAYED_IN.side` and `PLAYED_IN.goalsFor`.

**Loader-enforced invariants** (C10 — Community can only enforce uniqueness, so these are written correctly and then *verified*):
every `Match` has exactly two `PLAYED_IN` (one `HOME`, one `AWAY`, distinct teams); `p.goalsFor = q.goalsAgainst` across every pair; `outcome` and `points` agree with the goals; every `Team` has exactly one `HAS_TEAM`; every `Match` has exactly one `IN_STAGE`; `Match` scalar copies equal their `Stage`/`Competition` source values; no orphan nodes.

**How the schema answers the query set:**

| # | Shape | Notes |
|---|---|---|
| U1 | `(t:Team {teamId:$id})-[p:PLAYED_IN]->(m)<-[q:PLAYED_IN]-(o:Team) WHERE o<>t` | Single pattern, no `UNION`, no `CASE`. **AC17.** |
| U2 | `(a:Team{teamId:$a})-[pa:PLAYED_IN]->(m)<-[pb:PLAYED_IN]-(b:Team{teamId:$b})` | Single pattern, `ORDER BY m.date`. **AC17.** |
| U3 | U1 + `ORDER BY m.date` + running total via `reduce` over the collected list | `p.outcome` already present; no APOC. |
| U4 | U1 + group by `p.side` | |
| U5 | Two 2-hop patterns + list intersection, or `PLAYED_AGAINST` intersection | Both documented. |
| U6 | `shortestPath((a)-[:PLAYED_AGAINST*..6]-(b))` | Trivial with the derived layer; also expressible as `[:PLAYED_IN*..12]` through `Match` without it. |
| U7 | `(c:Club{clubId:$c})-[:HAS_TEAM]->(t)-[:PLAYED_IN]->(m)<-[q]-(o)` | One query spans all brackets. **AC18.** |
| U8 | `(v:Venue{venueKey:$k})<-[:PLAYED_AT]-(m)` | |
| U9 | U1 + `-[:IN_STAGE]->(s:Stage)`, group by `s.phase` | **AC19.** |
| U10 | `sum(p.points)`, `sum(p.goalsFor)` … grouped per `Stage`, compared to `PARTICIPATED_IN` | **AC8.** |
| U11 | `MATCH (m:Match) WHERE m.bracket=$b AND m.tier=$t ORDER BY m.goalMargin DESC` | Index-backed node scan, no traversal. |

---

## Task breakdown (sequenced)

### Phase A — Foundation

**T1. Project skeleton, tooling, config, Docker.**
Create `pyproject.toml` (uv), `src/dkfr/` package with `__version__`, `vocab.py` enums, `config.py`, a stub `cli.py`, `docker-compose.yml`, `.env.example`, `.gitignore` (with `data/`), README skeleton.
*Verify:* `uv run dkfr --help` lists all subcommands; `docker compose up -d` and Neo4j Browser responds on :7474; `git status` shows `data/` ignored (**AC21**).

**T2. Fetch/cache layer.**
`fetch/robots.py`, `fetch/cache.py`, `fetch/client.py`, request logging, `dkfr fetch --url` for one-off use.
*Verify:* `tests/test_fetch_politeness.py` green against `pytest-httpx` — disallowed path raises, consecutive fetches are ≥2s apart, UA contains project name + contact and no browser string, second fetch of a cached URL issues zero requests. One real fetch of `https://www.dbu.dk/resultater/pulje/473829/kampprogramFuld` lands in the cache with a valid sidecar. Inspect `data/logs/requests-*.jsonl` (**AC5/AC6**).

**T3. Discovery spike — the decision gate.** *(This is the spec's "discovery pass"; it is a real task, not a preamble.)*
Using T2's fetcher (polite, cached), fetch a deliberate sample: Superliga Grundspil `473806` + Mesterskabsspil `498492`, Herre-DS `473829`, U19 Drenge `473921`, U16 Piger `474480`, A-Liga — across `kampprogramFuld`, `stillingFuld`, `holdoversigt`, plus one `raekke` page. Write `docs/specs/dk-results-scraper/discovery-notes.md` answering, each with cited evidence:

1. **Q6 (blocking for Decision 3):** does the numeric teamId in `/resultater/hold/<teamId>_<puljeId>/info` stay identical for the same team across Grundspil and Mesterskabsspil? Check ≥3 teams × 2 puljer.
2. Do `kampprogramFuld` rows hyperlink team cells to `/resultater/hold/...` and/or the row to `/resultater/kamp/<matchId>_<puljeId>/`?
3. **Q5:** does the same `Kampnr` value appear in two different puljer?
4. Is `Kampnr` always present as a column? (The U19 sample suggests not.)
5. Where does the penalty text live — inside the `Resultat` cell, or a separate cell/column?
6. What status/marker vocabulary appears (`Udsat`, `Afbrudt`, `Annulleret`, `WO`, …)?
7. Exact `stillingFuld` column headers, and exact `kampprogramFuld` headers per bracket.
8. Do any puljer render reserve/second teams (`X 2`, `X (2)`, `X II`)?
9. Does `/resultater/raekke/<id>/` expose pulje hyperlinks in server-rendered HTML (an optional R2.1 supplement to the manual manifest)?
10. What is the exact pulje-title format, for `manifest verify`?

*Verify:* every question answered yes/no with a quoted snippet; the team-key branch (`dbu:` vs `name:`) is chosen and recorded. **Do not start T5/T6 before this is written down.**

**T4. Manifest schema, seed list, and verifier.**
`manifest.py` models + `manifest/puljer.yaml` hand-curated with every in-scope competition × phase × group. Expect ~70 entries: 5 men's tiers (Superliga 2–3 phases, 1. Div 3, 2. Div 3, 3. Div 2–3, DS 4 groups + phases), A-Liga + B-Liga with playoffs, and 4 youth ligaer. Implement `dkfr manifest verify`.
*Verify:* **AC1** — `dkfr manifest verify` reports every entry resolving to a live pulje whose title matches the declared competition, phase, and season code `(2026)`; zero unmatched. This is the most human-labour-intensive task in the project and its output is the artefact everything downstream depends on.

### Phase B — Extraction

**T5. Value parsers.**
`parse/values.py` + `tests/test_values.py`, table-driven across every C8 variation plus everything T3 found.
*Verify:* all variants parse; the weekday-vs-date cross-check fires on a deliberately corrupted input; unrecognized result text produces an issue rather than a silent `None`.

**T6. Table extractors and the full parse pass.**
`parse/tables.py`, `fixtures.py`, `standings.py`, `teams.py`, `issues.py`. Then `dkfr fetch` for all manifest puljer (3 requests each, ~210 total, ~10 min at 2s spacing) and parse the full cache.
*Verify:* **AC2** — per-pulje parsed match count equals the source page's row count for all puljer; **AC11** — `data/reports/parse-issues.json` exists, error-severity count is zero, warning rate under threshold, and the run fails loudly when the threshold is breached (test with an injected bad row).

**T7. Name normalization, resolver, and curated alias/club files.**
`normalize/names.py`, `normalize/resolver.py`, `manifest/aliases.yaml`, `manifest/clubs.yaml`, `dkfr names review`. Iterate: run, read the unresolved report, promote suggestions into the alias file, re-run.
*Verify:* **AC10** — unresolved-names report is empty after curation; a test asserts the same team in Grundspil and Mesterskabsspil resolves to one `teamId`, and the same short name in men's senior vs U19 resolves to two; a known multi-bracket club (FC København) groups ≥3 teams under one `clubId`.

**T8. Normalized records and deterministic writers.**
`normalize/records.py`, `normalize/writer.py`. Emit `matches.jsonl`, `puljer.json`, `teams.json`, `clubs.json`, `venues.json`.
*Verify:* **AC3** — a test asserts every match record carries the full required field set; **AC7** — `dkfr parse` twice with a warm cache produces byte-identical files and the request log shows zero network calls. Also freeze `tests/golden/matches.sample.jsonl` here — **this is the contract artefact that unblocks the parallel graph workstream.**

### Phase C — Graph

**T9. Schema and driver plumbing.**
`cypher/schema.cypher`, `load/driver.py`, `load/schema.py`, `dkfr load --schema-only`.
*Verify:* **AC12** — `SHOW CONSTRAINTS` and `SHOW INDEXES` match the file exactly; re-applying is a no-op.

**T10. Loader.**
`load/loader.py` — batched `UNWIND` + `MERGE`, ordered Competition → Season → Stage → Club → Team → Venue → Match → PLAYED_IN → PARTICIPATED_IN, with pre-write assertions (home ≠ away, exactly two sides per match).
*Verify:* **AC14** — load twice, node and relationship counts identical, no duplicates; **AC15** — graph counts reconcile with JSON record counts.

**T11. Post-load validation harness.**
`cypher/validation.cypher` + `load/validate.py` + `dkfr validate`.
*Verify:* **AC13** and the full invariant list; every assertion returns empty; each assertion is proven to actually fire by temporarily corrupting one record.

**T12. Derived `PLAYED_AGAINST` layer.**
`cypher/derive.cypher` + `dkfr derive` (full drop-and-rebuild).
*Verify:* relationship count equals the distinct unordered team-pair count computed from `matches.jsonl`; running `derive` twice changes nothing.

**T13. Query set U1–U11.**
`queries/*.cypher` + `queries/runner.py` + `dkfr query <name>`.
*Verify:* **AC16** — all 11 run and return correct results against loaded data; **AC17** — a static test asserts `u01` and `u02` contain no `UNION` and no `CASE`, plus a human read confirming single-pattern; **AC18** — U7 against FC København returns opponents from senior, U19, and U17; **AC19** — U9 against a Superliga team returns distinct Grundspil and Mesterskabsspil rows.

### Phase D — Validation and hardening

**T14. Reconciliation reports.**
Standings reconciliation (U10 vs `PARTICIPATED_IN`) with `pointsCarryOver` awareness, plus a Superliga Grundspil spot-check against an independent source.
*Verify:* **AC8** — ≥5 puljer spanning different tiers and brackets reconcile exactly on played/won/drawn/lost/GF/GA/points; carry-over stages are reported separately with an explanation rather than as failures. **AC9** — sampled Superliga matches match the independent source with no discrepancies.

**T15. Documentation.**
`README.md` (per-stage instructions, manifest format, C1/C2 constraints, explicit no-republication statement), `docs/schema/model.md`.
*Verify:* **AC20/AC21** — a reader can run each stage from the README alone; `git status` confirms nothing under `data/` is tracked.

**T16. End-to-end acceptance sweep.**
`dkfr all` from a cold cache on a reset database, then again warm.
*Verify:* every AC1–AC21 checked off in a final run summary.

---

## Workstream split

The work is large but the dependency chain is mostly linear, and this is a solo project — so the recommendation is **one primary workstream with one optional fork**, not a genuine parallel split.

- **The fork point is T8.** Once `tests/golden/matches.sample.jsonl` and `normalize/records.py` are frozen, **Workstream B (extraction: T5–T8 refinement, T14 parsing side)** and **Workstream C (graph: T9–T13)** are independent — C can be built and tested entirely against the golden sample with no scraper present. That is also exactly the property G2/R3.1 demand, so building the fork is free.
- **T3 and T4 gate everything and cannot be parallelized.** T3 resolves the team-key branch; T4 is manual curation with no code dependency but total downstream dependency. If any effort is to be time-boxed and front-loaded, it is these two.

**Shared resources both workstreams must use, never duplicate:**

| Resource | Why it must be shared |
|---|---|
| `src/dkfr/vocab.py` | The single enum vocabulary. A drifted `phase` or `bracket` string between parser and loader is the most likely silent-corruption bug in this project. |
| `src/dkfr/normalize/records.py` | The [2]→[3] contract. The loader must read pydantic-validated records, not raw dicts. |
| `manifest/puljer.yaml` | Competition metadata source of truth for both stages. |
| `tests/golden/matches.sample.jsonl` | The synthetic fixture both workstreams test against. |
| `docs/schema/model.md` | Must agree with `cypher/schema.cypher` and `queries/*.cypher` on every label, type, direction, property, and enum value — the same discipline the prior-art repo enforces. |

---

## Risks and open questions

### Risks

**R-1 — Q6 (cross-pulje team ID stability) is unverified, and it is the single biggest unknown.**
*Impact:* determines whether team identity is free or requires curated alias work. *Mitigation:* T3 answers it empirically before any resolver code is written, and Decision 3 is designed with both branches so the answer changes a configuration flag, not the architecture. *Residual:* if IDs are unstable, T7 becomes several hours of manual alias curation instead of minutes. Plan for that as the pessimistic case.

**R-2 — Manifest completeness cannot be proven programmatically (C5).**
There is no robots-permitted way to enumerate puljer, so "did I find every pulje?" has no mechanical answer. *Mitigation:* `expectedTeams`/`expectedMatches` per manifest entry validated against the scrape; a coverage check asserting every competition known to split has ≥2 phase puljer; per-competition total match counts cross-checked against Wikipedia's season articles. *Residual:* accepted. A missing playoff pulje would be silently absent from the graph. The cross-check against Wikipedia's expected fixture counts is the strongest available detector and should be part of T14.

**R-3 — Points and goals carry over into playoff phases, so naive U10 reconciliation will "fail" correctly.**
The spec's own F2 notes 2. Division and A-Liga carry points forward into the playoff groups. A standings table for a Mesterskabsspil pulje therefore will **not** equal the sum of that pulje's own matches. *Mitigation:* the `pointsCarryOver: true` manifest flag; T14 compares only match-derived columns (played/GF/GA within the stage) for those puljer and reports points separately. AC8's five reconciling puljer should be chosen from non-carry-over stages. **This must not be discovered mid-implementation as a data bug.**

**R-4 — Denormalized properties can drift.**
`PLAYED_IN.goalsAgainst`/`outcome`/`points` and the `Match` scalar copies of stage/competition context are all derivable. *Mitigation:* single-writer discipline plus explicit validation assertions in T11. *Escape hatch:* if the assertions ever prove hard to hold, drop the derived fields and compute at query time — a one-line change per query, no schema change.

**R-5 — `Kampnr` may be absent, and its uniqueness scope is unproven (Q5).**
*Mitigation:* composite `matchKey` regardless of the answer, with a deterministic fallback key. The deliberate choice not to use a bare `matchNumber` key even if it proves globally unique is a small cost for immunity to a whole class of collision bug.

**R-6 — Committing real scraped HTML as test fixtures would violate C2/R3.7.**
*Decision:* `tests/fixtures/html/` contains **synthetic, hand-authored** markup reproducing the observed table structure and every format variation — no DBU content. Optional tests against real cached pages are marked and skip when `data/cache` is absent. This keeps the test suite committable regardless of whether the repo is public.

**R-7 — Site markup could change mid-project.**
*Mitigation:* header-text-driven extraction rather than CSS-class or positional selectors; the HTML cache means a change mid-project doesn't invalidate work already fetched. Once the cache is warm, the project is effectively immune (the season is closed and immutable — C13).

**R-8 — `tier` is not comparable across brackets.**
The direct consequence of Decision 1's option (b). *Mitigation:* documented convention that every `tier` filter or ordering must co-filter on `bracket`; the U11 query template demonstrates the correct form; `docs/schema/model.md` states it prominently.

**R-9 — Venue identity is lossy.**
Venue names are free-text and will vary in spelling. `venueKey` normalization will over- and under-merge. *Accepted* — U8 is the only dependent use case and it is low-stakes. Not worth an alias map.

**R-10 — Timezone and DST.**
The season spans a DST boundary. *Mitigation:* store both the local `date` and the UTC `kickoffAt` instant; never derive the matchday from the instant.

**R-11 — Multi-season readiness is designed for but untested (N3).**
`Team` keys are deliberately season-independent so identity persists. If a club renames between seasons, the additive path is `validFrom`/`validTo` on `HAS_TEAM`. Not built, not blocked.

### Open questions

**OQ-1 — Should the derived `PLAYED_AGAINST` layer be built (T12)?**
*Recommendation: yes.* It turns U6 (degrees of separation) from a variable-length traversal through `Match` nodes at depth ~12 into a trivial 3-hop `shortestPath`, and simplifies U5. It costs a few thousand relationships and one idempotent rebuild stage. The core schema does not depend on it — U5 and U6 are documented both with and without — so it can be dropped without consequence. *Decide before T12; non-blocking for everything else.*

**OQ-2 — Q4: pull cup competitions in now?**
*Recommendation: not in v1, but the design costs nothing to keep the door open.* `phase: CUP` is reserved, and adding Oddset Pokalen / Kvinde-LP later is a manifest-rows-only change with zero schema work. They would meaningfully enrich U6 by connecting tiers that never meet in league play, so this is worth revisiting immediately after v1 lands. *Non-blocking.*

**OQ-3 — Q8: is the validation report a wanted deliverable?**
*Recommendation: yes, and the marginal cost is now small.* T11's harness exists regardless (AC13/14/15 require it), so T14 is mostly report formatting on top of infrastructure already built. Scraped data without a validation oracle is data you cannot trust. *If the user says no, T14 shrinks to the AC8/AC9 spot-checks and the report writing is dropped.*

**OQ-4 — Neo4j image pin: `5.26-community` LTS vs the `2026.xx` calver line?**
*Recommendation: 5.26 LTS.* Longest support window, most stable documentation, and every feature this design uses (relationship-property range indexes, composite uniqueness constraints) predates it. *Trivially reversible — one line in `docker-compose.yml`.*

**OQ-5 — Should T3 be allowed to fetch more broadly than the sample listed?**
The discovery spike's value scales with sample breadth, but every page is a request. *Recommendation:* cap T3 at ~20 requests across the six brackets; it is already polite and the pages are cached for later reuse by T6.

**OQ-6 — Does the user want `expectedMatches` filled in for every manifest entry, or only where a format is publicly documented?**
Playoff pulje fixture counts may not be knowable before fetching. *Recommendation:* make the field nullable, fill it where Wikipedia documents the format (which covers most men's tiers and A-Liga), and treat a null as "no expectation to check" rather than a validation failure.

