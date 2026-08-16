# Spec: Danish Football Results Scraper → Graph Database (2025/26)

**Status:** Draft for architect review
**Author:** analyst
**Date:** 2026-08-16
**Repo:** `/Users/teislebeck/dk-football-results-graph`

---

## Summary

Build a pipeline that scrapes every match result from the nationally-administered Danish football competitions for the **2025/26 season**, normalises them into a structured intermediate format (JSON), and loads them into a graph database so that traversal queries — "which teams has team X played, and what were the results" — are cheap and natural to express.

Source of record is the unified DBU results system at `https://www.dbu.dk/resultater/`, which serves every national tier and every age/gender bracket off one consistent, server-rendered `pulje` (pool) page structure. One parameterised scraper covers all of them.

Three findings from research materially change the shape of the work versus the initial framing, and the architect should treat these as settled inputs:

1. **The unit of scraping is a "pulje", not a "league", and leagues split into multiple puljer.** Nearly every national competition runs a `Grundspil` (regular season) followed by separate `Mesterskabsspil`/`Oprykningsspil`/`Nedrykningsspil` phases, each with its **own, non-contiguous pulje ID**. Superliga 2025/26 is at least pulje `473806` (Grundspil) and `498492` (Mesterskabsspil). ID ranges are not scannable.
2. **The season is complete and static.** 2025/26 ran roughly 18 July 2025 – mid-June 2026. This is a one-shot historical archive job, not a live-updating feed. That removes incremental-sync complexity and makes a curated seed list of pulje IDs a legitimate, robust design option.
3. **Two of the six brackets are misnamed in the intake.** The girls' national age groups are **U19 Piger and U16 Piger**, not U19/U17 — DBU replaced the U18 girls rows with U19 DM rows in 2023, and the second girls' tier is U16 DM. Boys are U19/U17. Same six brackets, corrected labels.

---

## Business context

**Why this matters.** Danish football results below the Superliga are effectively invisible as data. DBU publishes them, but only as per-pulje HTML tables with no bulk export, no public API, and no cross-competition view. Commercial sports-data APIs stop at the top one or two tiers. So the questions that are trivial to ask about the Premier League — "who has this club actually played this season, across all its teams and age groups?", "what connects these two clubs?" — are currently unanswerable for the Danish pyramid without manual page-by-page browsing.

**Who it's for.** A solo developer / football-data enthusiast (the repo owner), building a personal analytical dataset. There is no external customer, no SLA, and no commercial deployment in this project. This is explicitly *not* the customer-benchmarking use case that the separate `football-graph-schema` repo was built for.

**The problem it addresses.** Turning a fragmented, navigation-only public website into a queryable relational structure. The specific opportunity is the *graph* framing: match results are naturally a network (teams as nodes, matches as edges), and questions about that network — head-to-head history, common opponents, degrees of separation, cross-bracket club connections — are awkward in SQL and natural in Cypher. Loading the same data into a relational store would satisfy the letter of "structure the results" while missing the point.

**Why now / why this scope.** A completed season is a clean, bounded, immutable target — the ideal first dataset. Scope stops at the nationally-administered tiers because a stage-0 feasibility check flagged that the six DBU regional unions run their own differently-structured sites with degrading data quality, which would multiply the scraper surface for the lowest-value data.

---

## Goals / Non-goals

### Goals

- **G1.** Scrape complete match-level results for the 2025/26 season across all in-scope national competitions and all six age/gender brackets.
- **G2.** Produce a durable, structured, human-inspectable intermediate dataset (JSON) that is independent of the graph database — re-loadable without re-scraping.
- **G3.** Load that dataset into a graph database with a schema that makes team-to-team traversal the primary, cheapest access path.
- **G4.** Support the traversal query patterns in "Acceptance criteria → Query patterns" without schema changes.
- **G5.** Fetch politely and legally: respect `robots.txt`, rate-limit, cache, identify honestly, and keep the resulting dataset private.
- **G6.** Be re-runnable and idempotent — a second run over the same season yields the same graph, not duplicates.

### Non-goals

- **N1.** Regional/amateur tiers below the national pyramid (the six DBU regional union sites). Likely future phase; do not design for it now, but do not actively preclude it.
- **N2.** Any live / in-play / incremental update mechanism. The target season is closed.
- **N3.** Seasons other than 2025/26. The schema should not make adding 2024/25 later *hard*, but multi-season ingestion is not built or tested here.
- **N4.** Player-level data (lineups, goalscorers, cards) in the initial deliverable — see Constraints C6 for the GDPR reasoning. Match detail pages carry it; the schema should leave room, but the first cut is match-level.
- **N5.** Any web UI, dashboard, API, or visualisation layer. Query access is via the graph DB's own client (Cypher shell / Neo4j Browser).
- **N6.** Any commercial use, redistribution, or republication of the scraped data — this is explicitly precluded by DBU's terms (Constraint C2).
- **N7.** Reuse or extension of `/Users/teislebeck/football-graph-schema`. That repo's model is optional inspiration only; none of its commercial fields (`isCustomer`) belong here.
- **N8.** Cup competitions (Oddset Pokalen, Kvinde-LP). They exist on the same pulje system (e.g. pulje `462529`) and are cheap to add later, but they are not league results and are out of scope for v1. Flagged as an open question.

---

## Research findings

All URLs retrieved **2026-08-16**.

### F1. The `pulje` page is the correct scrape unit, and it is server-rendered

Every national competition, at every tier and bracket, is served from `https://www.dbu.dk/resultater/pulje/<id>/<view>`. Confirmed views:

| View | Content |
|---|---|
| `/stilling`, `/stillingFuld` | Standings table (K, V, U, T, Score, P) |
| `/kampprogram` | Fixture/results table |
| `/kampprogramFuld` | **Full season fixtures, all rounds, single page, no pagination** |
| `/holdoversigt` | Team list, with links to `/resultater/hold/<teamId>_<puljeId>/info` |
| `/topscorer` | Top scorers |
| `/regler` | Rules |

`kampprogramFuld` is the key endpoint: it renders the entire season's fixtures in one continuous table with **no pagination**, meaning **one HTTP request yields one pulje's complete results**.

Confirmed table columns: `Kampnr` (match number), `Dato`, `Tid`, `Hjemme`, `Ude`, `Spillested` (venue), `Resultat`.

Verbatim example rows (U19 Drenge Ligaen, pulje 473921):
```
fre.15-08 2025 | 15:00 | Vejle | FC København | VB Parken | 2 - 2 | Straffesparkskonkurrence 4 - 5
lør.16-08 2025 | 12:00 | Esbjerg | FC Midtjylland | Tjæreborg IF's Anlæg | 1 - 2
```
Note the **penalty-shootout suffix** on row 1 — the result cell is not always a simple `X - Y`.

Verbatim example rows (Herre-DS Pulje 4, pulje 473829):
```
909802 | lør.09-08 2025 | 13:00 | Holstebro B | Fuglebakken KFUM | Krøyer Park | 4-2
909803 | lør.09-08 2025 | 13:30 | Nørresundby FB | VRI | Nordjyske Bank Arena | 3-2
```
Note score formatting differs between puljer (`2 - 2` vs `4-2`) — the parser must be tolerant.

Content is server-rendered HTML with data embedded directly; no JavaScript execution is required to read fixtures or standings.

- https://www.dbu.dk/resultater/pulje/473921 (retrieved 2026-08-16)
- https://www.dbu.dk/resultater/pulje/473921/kampprogram (retrieved 2026-08-16)
- https://www.dbu.dk/resultater/pulje/473829/kampprogramFuld (retrieved 2026-08-16)
- https://www.dbu.dk/resultater/pulje/473829/stilling (retrieved 2026-08-16)

### F2. Leagues split into multiple puljer with non-contiguous IDs

This is the single most important structural finding.

- **Superliga 2025/26**: `473806` = "3F Superliga - Grundspil 2025/26 (2026)"; `498492` = "3F Superliga - Mesterskabsspil 2025/26 (2026)". A Nedrykningsspil pulje almost certainly exists too. Note the ID gap: ~25,000.
- **1. Division (Betinia Liga) 2025/26**: 12 teams, 22-round group stage, then splits into a 6-team promotion playoff and a 6-team relegation playoff, 10 further matches each.
- **2. Division 2025/26**: 12 teams, 22 rounds, then promotion group + relegation group with points and goals carried over.
- **A-Liga (women) 2025/26**: 8 teams, 14-match double round-robin, then a 6-team championship play-off (scores carry over) plus a qualification play-off against the top 4 from B-Liga.
- **Danmarksserien 2025/26**: 4 parallel puljer (`473829` is Pulje 4), plus promotion/relegation phases.

The ID-block clustering (`4738xx`/`4739xx`/`4744xx` for pre-season puljer, `4984xx` for spring-created playoff puljer) reflects *creation time*, not competition membership. **Scanning a contiguous ID range is not a viable discovery strategy** and would also be an unacceptable request-volume pattern.

- https://www.dbu.dk/resultater/pulje/473806 (retrieved 2026-08-16)
- https://www.dbu.dk/resultater/pulje/498492/karantaener (via search result, retrieved 2026-08-16)
- https://en.wikipedia.org/wiki/2025%E2%80%9326_Danish_2nd_Division (retrieved 2026-08-16)
- https://en.wikipedia.org/wiki/2025%E2%80%9326_Danish_1st_Division (via search result, retrieved 2026-08-16)
- https://en.wikipedia.org/wiki/2025%E2%80%9326_A-Liga (retrieved 2026-08-16)

### F3. The men's pyramid has five national tiers, not four — the intake's tier labels are off by one

Confirmed structure for 2025/26:

| Tier | Competition | Format |
|---|---|---|
| 1 | 3F Superliga | 12 teams |
| 2 | 1. Division / Betinia Liga | 12 teams |
| 3 | 2. Division | 12 teams |
| 4 | **3. Division (CampoBet 3. Division)** | 12 clubs, nationwide since 2021/22 |
| 5 | Danmarksserien (Herre-DS) | 4 groups |

3. Division was re-established as a nationwide tier in 2021/22 and gained its first title sponsor (Soft2Bet / CampoBet) for 2025/26 and 2026/27. Denmark Series sits **below** it as tier 5, with three clubs promoted from DS to 3. Division each season.

The intake describes scope as "Superliga, 1st Division, 2nd Division, and Denmark Series (3rd tier)". Denmark Series is the 5th tier, and 3. Division sits inside the stated boundary ("nationally-administered tiers down to Denmark Series") but was not named. See Open Question Q1.

- https://en.wikipedia.org/wiki/Denmark_Series (retrieved 2026-08-16)
- https://da.wikipedia.org/wiki/3._division_(fodbold) (via search result, retrieved 2026-08-16)
- https://www.dbu.dk/turneringer-og-resultater/landsdaekkende-turneringer-herrer/danmarksserien/oprykning-fra-herre-ds-til-3-division/ (via search result, retrieved 2026-08-16)
- https://www.dbu.dk/turneringer-og-resultater/landsdaekkende-turneringer-herrer/betinia-liga/ (via search result, retrieved 2026-08-16)

### F4. Bracket labels: the women's/girls' side differs from the intake

- **Women's senior**: the top division was **renamed from Kvindeligaen to A-Liga** effective 2025/26, with **B-Liga** as tier 2. Prior-season puljer confirm the same pulje system (`444579` = Gjensidige Kvindeliga 2024/25; `461618`).
- **Girls' youth**: national age groups are **U19 Piger** (pulje `474402` confirmed for 2025/26) and **U16 Piger** (pulje `474480` = "U16 Piger Division 2025/26"). DBU replaced the U18 rows with two new **U19 DM** rows from summer 2023; the second national girls' tier is **U16 DM**. There is **no national U17 girls competition**.
- **Boys' youth**: **U19 Drenge Ligaen** (`473921`) and **U17 Drenge Ligaen** (`473922`), both confirmed on the same system.

So the six brackets are: men's senior, U19 Drenge, U17 Drenge, women's senior, **U19 Piger**, **U16 Piger**.

- https://en.wikipedia.org/wiki/2025%E2%80%9326_A-Liga (retrieved 2026-08-16)
- https://www.dbu.dk/resultater/pulje/474480/stillingFuld (via search result, retrieved 2026-08-16)
- https://www.dbu.dk/resultater/pulje/474402/stillingFuld (via search result, retrieved 2026-08-16)
- https://www.dbu.dk/nyheder/2023/april/ny-dbu-turneringsstruktur-for-u16-og-u19-dm-piger/ (via search result, retrieved 2026-08-16)
- https://www.dbu.dk/turneringer-og-resultater/love-og-regler/landsdaekkende-turneringer/turneringspropositioner/propositioner-for-dbus-ungdomsturneringer-kvinder/ (via search result, retrieved 2026-08-16)

### F5. robots.txt permits `/resultater/pulje/` but explicitly forbids the search endpoints

`https://www.dbu.dk/robots.txt` (retrieved 2026-08-16), `User-agent: *` block, verbatim Disallow lines:

```
Disallow: /aspnet_client/
Disallow: /bin/
Disallow: /config/
Disallow: /data/
Disallow: /install/
Disallow: /masterpages/
Disallow: /python/
Disallow: /umbraco/
Disallow: /umbraco_client/
Disallow: /usercontrols/
Disallow: /xslt/
Disallow: /turneringer_og_resultater/resultatsoegning/
Disallow: /landshold/landsholdsdatabasen/*.aspx*
Disallow: /resultater/kampsoegAdvanceret/
```

Key implications:

- `/resultater/pulje/*`, `/resultater/kamp/*`, `/resultater/klub/*`, `/resultater/raekke/*`, `/resultater/hold/*` are **not disallowed**.
- **`/resultater/kampsoegAdvanceret/` (advanced match search) IS disallowed** — the most obvious discovery mechanism is off-limits. So is the legacy `/turneringer_og_resultater/resultatsoegning/`.
- **No `Crawl-delay` directive** is present, so a rate limit is a politeness decision, not a stated requirement.
- Separate blocks fully disallow named agents: AhrefsBot, Baiduspider, Ezooms, MJ12bot, YandexBot, SemrushBot, GrapeshotCrawler, Proximic, and **Perl LWP**. Blocking a generic HTTP library user-agent shows DBU does filter on UA; the scraper must send an honest, descriptive, non-default UA and must not impersonate a browser.

### F6. DBU's terms of use restrict republication of scraped content

`https://www.dbu.dk/betingelser-og-vilkaar/` §A.5 "Immaterielle rettigheder" (retrieved 2026-08-16), verbatim:

> "Det er ikke tilladt helt eller delvist at optage, registrere, offentliggøre, dele eller gengive beskyttet indhold fra DBU's kanaler, DBU's arrangementer eller fra DBU's markedsføring og anden kommunikation uden DBU's forudgående skriftlige tilladelse."

> "Logoer og øvrige varemærker ikke må benyttes uden DBU's skriftlige tilladelse."

The only carve-out is "hvor brugen er udtrykkeligt tilladt i henhold til ufravigelig gældende lovgivning" (where mandatory applicable law expressly permits). There is no explicit personal-use exemption in the current text.

Practical reading for this project: private collection and analysis for personal use is low-risk and consistent with the project's stated non-commercial purpose; **publishing the scraped dataset (e.g. committing JSON dumps to a public repo, or publishing a derived site) is not.** Club crest/logo images must not be downloaded or stored.

### F7. There is no usable official API

DBU's only programmatic offering is the **KlubWeb API** at `https://clubservice.dbu.dk/`, which requires a per-club API key ordered through KlubOffice and is scoped to that club's own data. Its terms are explicitly restrictive:

> "data udelukkende bruges på vegne af klubben og til klubbens egne formål"

and third parties may not use the data "til egne formål, kommerciel udnyttelse, analyse, produktudvikling eller andre aktiviteter".

The API is therefore both technically unsuitable (club-scoped, not a results feed) and contractually unavailable for this use case. This confirms the feasibility check's conclusion. Public-page scraping is the only path.

- https://www.dbu.dk/klubservice/it-tilbud/data-fra-dbu-s-systemer/ (retrieved 2026-08-16)
- https://clubservicetest.dbu.dk/apiHelp (via search result, retrieved 2026-08-16)

### F8. Commercial APIs do not cover the scope — build, don't buy

- **football-data.org**: Danish Superliga is **not** in the free tier (12 competitions: UCL, PL, La Liga, Bundesliga, Serie A, Ligue 1, Eredivisie, Primeira Liga, Championship, Brasileirão, World Cup, Euros).
- **Sportmonks**: free tier covers exactly two leagues — **Danish Superliga** and Scottish Premiership.
- **openfootball/football.json**: public-domain CC0 fixtures/results in JSON, but Denmark coverage is not confirmed and the project is community-maintained with variable currency.

Even in the best case, a paid or free API covers tier 1 only. Tiers 2–5 and all four youth/women's brackets — i.e. the overwhelming majority of the target dataset — have no commercial source. **Recommendation: scrape everything from DBU for consistency.** Sportmonks' free Superliga feed is worth noting as an independent cross-check for validating the Superliga scrape (see Acceptance Criteria AC9), not as a data source.

- https://www.football-data.org/coverage (via search result, retrieved 2026-08-16)
- https://www.thestatsapi.com/blog/free-football-api-alternatives (via search result, retrieved 2026-08-16)
- https://github.com/openfootball/football.json (via search result, retrieved 2026-08-16)

### F9. Match detail pages are rich, but carry personal data

`https://www.dbu.dk/resultater/kamp/<matchId>_<puljeId>/kampinfo` (example: `769194_473921`, retrieved 2026-08-16) contains: match number, date, kickoff time, both teams, final score, penalty shootout score, status (`Færdigspillet`), venue with postcode/town/phone and specific pitch, **referee and both assistant referees by name**, goalscorers with minute, yellow cards, substitutions, half-time marker, **full starting XI and substitutes with squad numbers for both teams**, and team staff (coaches, medical, analysts).

The page also carries the notice:

> "Persondata vises ikke længere offentlig på bredde-kampe i disse rækker"

(personal data is no longer shown publicly for grassroots matches in these rows) — so DBU already suppresses personal data at lower levels, and exposes it at elite levels.

This is one HTTP request **per match**, versus one request per *pulje* for the fixtures table. Scraping detail pages for ~13,000 matches is a ~13,000× request multiplier over the ~100-request fixtures pass. Combined with the GDPR exposure of storing named minors' data (U16/U17/U19 brackets), this strongly argues for deferring detail-page scraping.

### F10. Graph database landscape — Neo4j remains the right default

- **Kùzu / KuzuDB, the leading embedded Cypher graph DB, is dead.** The GitHub repo was archived in October 2025 after Apple acqui-hired the team (confirmed months later by an EC filing). A community fork, **LadybugDB**, exists under a permissive licence and retains the Cypher dialect and columnar storage, but is young. **Do not select Kuzu.**
- **Neo4j** is actively maintained under calendar versioning: current Docker images include `2026.07.1-community` and `2026.06.0`, alongside the **5.26.x LTS** line. Community Edition supports uniqueness constraints (single and composite) and relationship-property range indexes; existence, node-key, and property-type constraints remain Enterprise-only.
- **Neo4j AuraDB Free**: documentation is inconsistent — the FAQ states 200k nodes / 400k relationships, the product page states 50k / 175k. Verify in the console before relying on it.
- Alternatives raised by the Kuzu fallout (ArcadeDB, FalkorDB, ArangoDB, Memgraph) are viable but offer no advantage for a single-user, ~25k-node dataset over Neo4j's superior tooling and documentation.

**Sizing estimate for this project:** ~13,000 matches → roughly 13k Match nodes + ~600 Team nodes + ~400 Club nodes + ~60 Competition/Phase nodes ≈ **~15–25k nodes and ~40–60k relationships** if match-level only. That fits comfortably in AuraDB Free even under the pessimistic 50k/175k reading. Adding player-level appearance data (≈22 players × 13k matches ≈ 290k relationships) would blow past **both** readings — a further reason to keep N4 out of v1, and a reason to prefer local Docker for headroom.

- https://www.theregister.com/2025/10/14/kuzudb_abandoned/ (via search result, retrieved 2026-08-16)
- https://gdotv.com/blog/kuzu-legacy-embedded-graph-database-landscape/ (via search result, retrieved 2026-08-16)
- https://hub.docker.com/_/neo4j (via search result, retrieved 2026-08-16)
- https://neo4j.com/docs/operations-manual/current/docker/introduction/ (via search result, retrieved 2026-08-16)
- https://neo4j.com/cloud/platform/aura-graph-database/faq/ (via search result, retrieved 2026-08-16)
- https://neo4j.com/docs/python-manual/current/performance/ (via search result, retrieved 2026-08-16)

### F11. Pulje discovery is the genuinely hard part

With `/resultater/kampsoegAdvanceret/` robots-disallowed (F5), discovery options are:

| Option | Assessment |
|---|---|
| **Curated seed list of pulje IDs** | Most robust. ~40–100 IDs, gathered once by hand/browser. Season is static (F2), so the list never goes stale. Zero discovery requests. **Recommended primary.** |
| `/resultater/raekke/<id>/` pages | A "række" (league) page groups its puljer — e.g. `/resultater/Raekke/80879` = Herre-DS, showing "Pulje 1..4", with a season selector covering 2001–2026. Not robots-disallowed. **But**: fetching it did not surface the pulje hyperlinks in the initial HTML, suggesting the pulje links may be rendered client-side. Must be verified at build time. |
| `/resultater/klub/<id>/kampprogram` | Club-scoped fixture lists exist and are not disallowed. Useful as a cross-check, not as primary discovery. |
| Contiguous ID scanning | **Rejected** — IDs are non-contiguous (F2) and this is an abusive request pattern. |

The `/resultater/pulje/<id>/stilling` page shows **no breadcrumb to a parent række and no sibling-pulje dropdown** in the server-rendered HTML, so upward/lateral navigation from a known pulje is not reliably available.

Note also that the site's season selector uses a **single year** (`2026`) to denote the 2025/26 season, matching the pulje title suffix "3F Superliga - Grundspil 2025/26 **(2026)**".

- https://www.dbu.dk/resultater/Raekke/80879 (retrieved 2026-08-16)
- https://www.dbu.dk/resultater/ (retrieved 2026-08-16)
- https://www.dbu.dk/resultater/pulje/473829/stilling (retrieved 2026-08-16)

---

## Requirements

### R1. Data model — what a match result must capture

The architect owns the graph schema; this section defines the **facts that must survive the pipeline**, not their node/relationship arrangement.

**Required per match:**

| Field | Notes |
|---|---|
| `matchNumber` | DBU `Kampnr`, e.g. `909802`, `769194`. Appears stable and globally unique, but **this is an assumption** — see Q5. Composite key `(puljeId, matchNumber)` is the safe fallback. |
| `puljeId` | Source pulje, e.g. `473829`. |
| `date` | Parsed to ISO date from `lør.09-08 2025` style. Danish weekday abbreviations. |
| `kickoffTime` | Local time, `Europe/Copenhagen`. Nullable. |
| `homeTeamName`, `awayTeamName` | As rendered on the source page. |
| `homeGoals`, `awayGoals` | Integers. Nullable when not played. Parser must handle both `2 - 2` and `4-2` (F1). |
| `penaltyHomeGoals`, `penaltyAwayGoals` | From the `Straffesparkskonkurrence 4 - 5` suffix. Nullable. |
| `status` | Enum, at minimum: `PLAYED`, `NOT_PLAYED`. Extend if the source exposes walkover / annulled / postponed markers — must be established during the discovery pass. |
| `venueName` | `Spillested`, e.g. `VB Parken`. Nullable. |
| `sourceUrl`, `fetchedAt`, `scraperVersion` | Provenance. Non-negotiable — this is scraped data and must be traceable to a page and a moment. |

**Required per pulje (competition context, denormalised onto or reachable from every match):**

| Field | Notes |
|---|---|
| `puljeId`, `puljeName` | e.g. `"Herre-DS 2025-26, Pulje 4 (2026)"` |
| `competitionName` | e.g. `"3F Superliga"`, `"Herre-DS"`, `"U19 Drenge Ligaen"` |
| `tier` | Integer 1–5 for men's senior; a distinct scheme for youth/women's — see Q2. |
| `phase` | Enum: `GRUNDSPIL`, `MESTERSKABSSPIL`, `OPRYKNINGSSPIL`, `NEDRYKNINGSSPIL`, `KVALIFIKATIONSSPIL`, `SINGLE`. **This is load-bearing** — without it, a Superliga team's Grundspil and Mesterskabsspil matches are indistinguishable (F2). |
| `groupLabel` | e.g. `"Pulje 4"`, for tiers with parallel groups. Nullable. |
| `season` | `"2025/26"`. |
| `gender` | `MEN` / `WOMEN`. |
| `ageBracket` | `SENIOR`, `U19`, `U17`, `U16`. |
| `administrator` | `DBU` or `Divisionsforeningen` — the pulje pages name the responsible body (Superliga and U19 Drenge Ligaen both route enquiries to Divisionsforeningen). |

**Explicitly optional / deferred (available on detail pages, out of scope for v1 per N4):** referee and assistants, attendance, goalscorers with minutes, cards, substitutions, lineups, team staff, half-time score, pitch designation, venue postcode/town.

**Entity requirements:**

- **Team vs Club must be distinguished.** "FC København" fields a men's senior team, a U19 Drenge team, and a U17 Drenge team — three distinct competing entities under one club. Traversal use case U7 depends on this split. The prior-art repo's `(:Club)-[:HAS_TEAM]->(:Team)` shape is a reasonable starting point.
- **Team identity across puljer must be resolved.** The same team appears in both Grundspil and Mesterskabsspil puljer and must be one node, not two. `/resultater/hold/<teamId>_<puljeId>/info` exposes a numeric team ID (e.g. `12963`) which may be the stable key — verify during discovery.
- **Club-name normalisation is required and will be imperfect.** Source pages render short names (`Vejle`, `Esbjerg`, `VRI`) that vary in form. Fuzzy matching will be needed; the pipeline must make its normalisation decisions **inspectable and overridable via a checked-in alias map**, not buried in code.
- **Standings tables should be captured too** — cheap (one extra request per pulje), and they serve as an independent validation oracle for the fixtures scrape (AC8).

### R2. Scraping approach

- **R2.1 Discovery.** Primary mechanism: a **checked-in, version-controlled seed manifest of pulje IDs** with their metadata (competition, tier, phase, bracket, group). Justified by F11 and by the season being static. The manifest is a first-class project artefact, human-readable and hand-editable. Optionally supplement with a `/resultater/raekke/<id>/` crawl if the architect verifies pulje links are present in server-rendered HTML.
- **R2.2 Fetch surface.** Per pulje: `GET /resultater/pulje/<id>/kampprogramFuld` (fixtures, complete, unpaginated) and `GET /resultater/pulje/<id>/stillingFuld` (standings, for validation). **~2 requests per pulje**, total ~80–200 requests for the whole season. This is a very small crawl.
- **R2.3 Politeness.** No `Crawl-delay` is specified (F5), so choose a conservative default: **≥2 seconds between requests, serial, no concurrency**. At ~200 requests this is a ~7-minute run — there is no performance justification for going faster.
- **R2.4 Identification.** Send an honest, descriptive `User-Agent` naming the project and a contact address. Do **not** spoof a browser UA — DBU blocks by UA (F5) and spoofing would be bad faith.
- **R2.5 robots.txt compliance.** Never request `/resultater/kampsoegAdvanceret/` or `/turneringer_og_resultater/resultatsoegning/`. Ideally parse and honour `robots.txt` programmatically rather than hard-coding the current rules.
- **R2.6 Response caching.** Cache raw HTML to disk keyed by URL, with the fetch timestamp. Iterating on the parser must not re-hit the site. This is the single most important politeness measure — parser development will involve dozens of passes over the same pages.
- **R2.7 Robustness.** Retry with exponential backoff on 5xx/timeouts, with a bounded retry count. Treat a 404 on a manifest pulje ID as a loud, run-failing error, not a silent skip.
- **R2.8 No image/asset fetching.** Do not download club crests or logos — F6 forbids logo reproduction, and they carry no analytical value.
- **R2.9 Parser tolerance.** Handle the confirmed format variations (score separators, penalty-shootout suffixes, Danish date/weekday formats, missing venue, unplayed fixtures). Unparseable rows must be **collected and reported**, never silently dropped.

### R3. Storage and output

- **R3.1 Intermediate format.** JSON (or JSON Lines for the match set). Must be complete enough to rebuild the entire graph with the scraper offline — this decouples parsing from loading and makes schema iteration cheap.
- **R3.2 Layering.** Keep raw HTML cache, parsed JSON, and loaded graph as three distinct, separately re-runnable stages. Re-running the loader must not require re-running the scraper.
- **R3.3 Graph database: Neo4j.** Confirmed as the right default (F10). Kùzu is explicitly ruled out (archived October 2025). Community Edition is sufficient; note that it cannot enforce existence/type constraints, so cardinality invariants (every match has exactly one home and one away team) must be enforced by the loader.
- **R3.4 Deployment: local Docker.** Recommended over AuraDB Free — no size ceiling, no network dependency, no account, trivially resettable during schema iteration, and it preserves headroom for a future player-level phase that would exceed Aura Free (F10). AuraDB Free remains a viable secondary if a hosted instance is wanted; the loader should not care which it targets (both speak Bolt).
- **R3.5 Idempotent loading.** `MERGE` on stable business keys so a re-run updates rather than duplicates (G6). Note the performance tradeoff — `MERGE` costs roughly double `CREATE` — but at ~13k matches, correctness wins outright.
- **R3.6 Constraints and indexes as code.** Uniqueness constraints on every business key, checked into the repo as `.cypher` and applied before load.
- **R3.7 Dataset must remain private.** Per F6: no committing scraped JSON dumps or HTML cache to a public repo. `.gitignore` the data directories, or keep the repo private, and say so explicitly in the README.

### R4. Traversal use cases

The user's framing — "team X has played team Y, with result Z" — expands to the following. **U1–U4 are the core; the schema must make them single-pattern Cypher queries.**

| # | Query pattern |
|---|---|
| **U1** | All opponents of team X in 2025/26, with each result and home/away side. |
| **U2** | Head-to-head: every match between team X and team Y, both legs, chronologically. |
| **U3** | Team X's full season results ordered by date, with W/D/L derived and running goal difference. |
| **U4** | Team X's record split by home vs away. |
| **U5** | Common opponents of teams X and Y (2-hop intersection) — the basis of "who has a comparable schedule". |
| **U6** | Degrees of separation: shortest path of "played against" hops between two teams, including across tiers where playoff structures connect them. |
| **U7** | Cross-bracket club traversal: all opponents faced by *any* team of club C, across men's senior, U19, and U17 — the query that most justifies the Club/Team split. |
| **U8** | All matches played at venue V. |
| **U9** | A team's path through the season's phases: which puljer it appeared in (Grundspil → Mesterskabsspil), and its record within each. Depends directly on `phase` being modelled (R1). |
| **U10** | Derived standings: reconstruct a pulje's table from its matches, for comparison against the scraped `stillingFuld` (validation, AC8). |
| **U11** | Biggest wins / highest-scoring matches, filterable by tier and bracket. |

---

## Constraints

- **C1 — robots.txt.** `/resultater/kampsoegAdvanceret/` and `/turneringer_og_resultater/resultatsoegning/` are disallowed; the pulje/kamp/klub/raekke/hold paths are not. No `Crawl-delay` is declared. DBU blocks specific user-agents including generic HTTP library UAs. (F5)
- **C2 — Terms of use.** DBU §A.5 forbids reproducing or sharing protected content without written permission, and forbids use of logos/trademarks. Private collection and personal analysis is the project's stated purpose and is defensible; **publication or redistribution of the dataset is not.** No logo scraping. (F6)
- **C3 — No official API.** KlubWeb API is club-key-gated and its terms forbid third-party use for "egne formål... analyse". Not an option. (F7)
- **C4 — No commercial API covers the scope.** Best case is Superliga-only. (F8)
- **C5 — Pulje discovery has no robots-permitted programmatic entry point.** The advanced search is disallowed and pulje pages carry no parent/sibling navigation in server-rendered HTML. A curated manifest is the pragmatic answer. (F5, F11)
- **C6 — GDPR / minors.** Match detail pages expose named individuals — including players in U16/U17/U19 competitions, i.e. minors — plus referees and staff. DBU itself already suppresses this for grassroots rows. Storing named minors' data in a personal database is a real privacy exposure with no offsetting benefit for the stated traversal use cases. **v1 must not scrape or store player-level personal data.** (F9, N4)
- **C7 — Request-volume asymmetry.** Fixtures are one request per *pulje* (~200 total); detail pages are one request per *match* (~13,000). Any future player-level phase is a 65× crawl and needs its own politeness plan.
- **C8 — Source formatting is inconsistent across puljer.** Score separators differ (`2 - 2` vs `4-2`), penalty results append free text, dates use Danish weekday abbreviations. Parser must be defensive. (F1)
- **C9 — Team name normalisation is inherently lossy.** Short display names will collide and vary; a checked-in alias map plus a manual-review step is required. Do not expect a fully automatic solution.
- **C10 — Neo4j Community cannot enforce existence, node-key, or property-type constraints.** Only uniqueness. Invariants must be loader-enforced and validated post-load. (F10)
- **C11 — AuraDB Free size limits are documented inconsistently** (200k/400k in the FAQ vs 50k/175k on the product page). If Aura is chosen, verify in-console. (F10)
- **C12 — Kùzu must not be selected.** Archived October 2025. (F10)
- **C13 — Season is closed and immutable.** Simplifies everything; also means any "live" design work is wasted effort. (F2)
- **C14 — Solo project, no budget stated.** Prefer free/local/open tooling; avoid anything requiring a paid tier or a support contract.

---

## Open questions

**Q1 — RESOLVED: include 3. Division.** User confirmed 2026-08-16: the men's senior pyramid in scope is Superliga, 1. Division, 2. Division, 3. Division, Danmarksserien — all 5 national tiers, no gap.

**Q2 — How should `tier` be encoded for non-men's-senior brackets?** Tier 1–5 is unambiguous for the men's senior pyramid. Women's senior is A-Liga / B-Liga (2 tiers). Youth brackets have a Liga plus divisions below. Options: (a) a single global `tier` integer scoped within each bracket, (b) a `tier` integer plus a `pyramid` discriminator, (c) no numeric tier, just competition name and an ordering hint. *Blocking for schema design; the architect may reasonably decide this.*

**Q3 — RESOLVED: top national league only per bracket.** User confirmed 2026-08-16: v1 covers exactly one competition per non-men's-senior bracket — U19 Drenge Ligaen, U17 Drenge Ligaen, A-Liga, B-Liga (women's senior, 2 tiers), U19 Piger, U16 Piger. Divisions below these (e.g. "U19 Drenge Øst 1 E") are out of scope for v1.

**Q4 — Include cup competitions?** Oddset Pokalen (`462529`) and Kvinde-LP are on the same pulje system, are cheap to add, and would meaningfully enrich U6 (degrees of separation) by connecting teams across tiers that never meet in league play. Currently N8 (out of scope). *Non-blocking — can be added post-v1 without schema change if `phase` supports a `CUP` value.*

**Q5 — Is `Kampnr` globally unique, or unique only within a pulje?** Observed values differ in magnitude across competitions (`769194` for U19, `909802` for DS), which is consistent with global uniqueness but does not prove it. Affects primary key choice. **Recommendation: use the composite `(puljeId, matchNumber)` unless the discovery pass proves global uniqueness** — composite is safe either way. *Non-blocking; resolve empirically during discovery.*

**Q6 — Is `/resultater/hold/<teamId>_<puljeId>/info` a stable cross-pulje team ID?** If `teamId` (e.g. `12963`) is stable across puljer and seasons, team identity resolution becomes trivial and the fuzzy-matching problem (C9) largely disappears. Worth 15 minutes of verification early — it could remove a whole category of work. *Non-blocking but high-value; verify in the discovery pass.*

**Q7 — RESOLVED: local Docker Neo4j.** User confirmed 2026-08-16, per R3.4's recommendation.

**Q8 — Does the user want a validation report as a deliverable?** AC8/AC9 propose reconciling scraped fixtures against scraped standings and (for Superliga) an independent source. This is meaningful extra work. Worth it in the analyst's view — scraped data with no validation oracle is data you cannot trust — but it is a scope call. *Non-blocking.*

**Q9 — Confirm the corrected bracket labels.** The six brackets become men's senior, U19 Drenge, U17 Drenge, women's senior, **U19 Piger**, **U16 Piger**. There is no national U17 girls competition (F4). Flagging for acknowledgement, not debate. *Non-blocking.*

---

## Acceptance criteria

**Data completeness**

- **AC1.** A checked-in pulje manifest exists covering every in-scope competition × phase × bracket for 2025/26, each entry carrying competition name, tier, phase, group label, gender, and age bracket. Every entry resolves to a live pulje page.
- **AC2.** For every pulje in the manifest, the scraper produces a fixtures record set whose match count matches the count of rows on the source `kampprogramFuld` page. Zero silently dropped rows.
- **AC3.** Every match in the output carries: date, home team, away team, home goals, away goals (or an explicit not-played status), pulje ID, competition, tier, phase, season, gender, age bracket, source URL, and fetch timestamp.
- **AC4.** Penalty-shootout results are captured as separate fields, not merged into or lost from the normal score.

**Scraper behaviour**

- **AC5.** The scraper never issues a request to a robots-disallowed path. Demonstrable by inspecting the request log.
- **AC6.** Requests are serial with a ≥2s delay, and send a descriptive non-spoofed User-Agent.
- **AC7.** A full re-run with a warm HTML cache issues **zero** network requests and reproduces byte-identical parsed JSON.

**Data quality**

- **AC8.** For at least 5 puljer spanning different tiers and brackets, standings derived from the scraped matches (U10) reconcile exactly with the scraped `stillingFuld` table on played/won/drawn/lost/goals-for/goals-against/points.
- **AC9.** Superliga Grundspil results are spot-checked against at least one independent source (e.g. the Wikipedia 2025/26 Superliga results grid, or the Sportmonks free Superliga feed) with no discrepancies in the sampled matches.
- **AC10.** Team-name normalisation is driven by a checked-in alias map. Any team name the pipeline cannot confidently resolve is surfaced in an unresolved-names report, not silently guessed.
- **AC11.** A parse-failure report lists every row the parser could not fully interpret; the run fails loudly if this exceeds a defined threshold.

**Graph**

- **AC12.** Uniqueness constraints are applied from a checked-in `.cypher` file before any data load.
- **AC13.** Post-load validation confirms every Match node has exactly two participating teams, one home and one away, and that the two are distinct.
- **AC14.** Loading the same JSON twice produces an identical graph — identical node and relationship counts, no duplicates (G6).
- **AC15.** Node and relationship counts in the graph reconcile with counts in the intermediate JSON.

**Query patterns**

- **AC16.** Each of U1–U11 is expressible as a documented Cypher query, checked into the repo, returning correct results against the loaded data.
- **AC17.** U1 (opponents-and-results for a team) and U2 (head-to-head) each run in a single traversal pattern with no `UNION`, no `CASE` on relationship type, and no post-filtering in application code.
- **AC18.** U7 (cross-bracket club traversal) works: querying a club that fields men's senior, U19, and U17 teams returns opponents from all three brackets in one query.
- **AC19.** U9 correctly distinguishes a Superliga team's Grundspil record from its Mesterskabsspil record.

**Documentation / hygiene**

- **AC20.** A README documents how to run each stage independently (scrape, parse, load), the manifest format, the source and terms constraints from C1/C2, and the explicit statement that the dataset is not to be republished.
- **AC21.** Scraped data directories are excluded from version control, or the repo is private, per R3.7.

---

## Recommended pipeline

**Full pipeline (architect → developer → reviewer).**

This spans three separable subsystems (fetch/cache layer, HTML parser and normalisation, graph loader and schema) whose interfaces need deliberate design, and it carries at least three genuine tradeoffs an architect should reason about rather than a developer discover mid-implementation: how to model competition phase and tier so that Grundspil and Mesterskabsspil are distinguishable without fragmenting team identity (F2, U9, Q2); whether per-side match facts live on nodes or relationships, given that U1/U2/U6 are the hot paths and U17 forbids `CASE`-on-relationship-type workarounds; and how team-identity resolution across puljer is structured, which changes shape entirely depending on the answer to Q6.

Q1, Q2, and Q3 should be answered by the user before the architect starts — they determine what goes in the manifest and therefore what the schema must accommodate.

---

## Sources

- [dbu.dk robots.txt](https://www.dbu.dk/robots.txt)
- [DBU Betingelser og Vilkår](https://www.dbu.dk/betingelser-og-vilkaar/)
- [DBU Stillinger og resultater](https://www.dbu.dk/resultater/)
- [U19 Drenge Ligaen 2025/26 (pulje 473921)](https://www.dbu.dk/resultater/pulje/473921)
- [U19 Drenge Ligaen kampprogram](https://www.dbu.dk/resultater/pulje/473921/kampprogram)
- [3F Superliga Grundspil 2025/26 (pulje 473806)](https://www.dbu.dk/resultater/pulje/473806)
- [Herre-DS 2025-26 Pulje 4 kampprogramFuld](https://www.dbu.dk/resultater/pulje/473829/kampprogramFuld)
- [Herre-DS 2025-26 Pulje 4 stilling](https://www.dbu.dk/resultater/pulje/473829/stilling)
- [Herre-DS række page](https://www.dbu.dk/resultater/Raekke/80879)
- [Match detail page example](https://www.dbu.dk/resultater/kamp/769194_473921/kampinfo)
- [Data fra DBU's systemer (KlubWeb API)](https://www.dbu.dk/klubservice/it-tilbud/data-fra-dbu-s-systemer/)
- [U16 Piger Division 2025/26 (pulje 474480)](https://www.dbu.dk/resultater/pulje/474480/stillingFuld)
- [U19 Piger 2025/26 (pulje 474402)](https://www.dbu.dk/resultater/pulje/474402/stillingFuld)
- [Ny DBU turneringsstruktur for U16 og U19 DM piger](https://www.dbu.dk/nyheder/2023/april/ny-dbu-turneringsstruktur-for-u16-og-u19-dm-piger/)
- [Oprykning fra Herre-DS til 3. division](https://www.dbu.dk/turneringer-og-resultater/landsdaekkende-turneringer-herrer/danmarksserien/oprykning-fra-herre-ds-til-3-division/)
- [1. Division / Betinia Liga](https://www.dbu.dk/turneringer-og-resultater/landsdaekkende-turneringer-herrer/betinia-liga/)
- [Wikipedia: Denmark Series](https://en.wikipedia.org/wiki/Denmark_Series)
- [Wikipedia: 2025–26 Danish 2nd Division](https://en.wikipedia.org/wiki/2025%E2%80%9326_Danish_2nd_Division)
- [Wikipedia: 2025–26 A-Liga](https://en.wikipedia.org/wiki/2025%E2%80%9326_A-Liga)
- [Wikipedia: 3. division (fodbold)](https://da.wikipedia.org/wiki/3._division_(fodbold))
- [football-data.org coverage](https://www.football-data.org/coverage)
- [Free football API alternatives comparison](https://www.thestatsapi.com/blog/free-football-api-alternatives)
- [openfootball/football.json](https://github.com/openfootball/football.json)
- [The Register: KuzuDB abandoned](https://www.theregister.com/2025/10/14/kuzudb_abandoned/)
- [Kuzu's legacy and embedded graph DB landscape](https://gdotv.com/blog/kuzu-legacy-embedded-graph-database-landscape/)
- [Neo4j official Docker image](https://hub.docker.com/_/neo4j)
- [Neo4j Docker introduction](https://neo4j.com/docs/operations-manual/current/docker/introduction/)
- [Neo4j AuraDB FAQ](https://neo4j.com/cloud/platform/aura-graph-database/faq/)
- [Neo4j Python driver performance recommendations](https://neo4j.com/docs/python-manual/current/performance/)

