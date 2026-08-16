# dk-football-results-graph

A pipeline that scrapes Danish football (soccer) match results for the
**2025/26 season** from the nationally-administered DBU competitions
(`dbu.dk`), normalizes them into structured JSON, and loads them into a
local Neo4j graph database for traversal queries (team-vs-team history,
head-to-head, cross-bracket club connections).

Full background, research, and design rationale live in
[`docs/specs/dk-results-scraper/spec.md`](docs/specs/dk-results-scraper/spec.md) and
[`docs/specs/dk-results-scraper/design.md`](docs/specs/dk-results-scraper/design.md).
This README covers only how to run it.

**Status: T1-T16 implemented and verified against a real scrape.** See the
"Implementation status" section at the bottom for the full account.

---

## IMPORTANT — read before running anything

- **This project scrapes `dbu.dk`.** It respects `robots.txt`, sends an
  honest, descriptive `User-Agent` (project name + a real contact email —
  you must set `DBU_CONTACT_EMAIL`, there is no default), and never hits
  the disallowed search endpoints (`/resultater/kampsoegAdvanceret/`,
  `/turneringer_og_resultater/resultatsoegning/`). Requests are strictly
  serial with a minimum 2-second gap between actual network hits (cache
  hits are free).
- **The scraped dataset must never be published or redistributed.** Per
  DBU's terms of use (§A.5), reproducing or sharing protected content
  from dbu.dk without written permission is not allowed. This project is
  for private, personal, non-commercial analysis only. Do not commit
  scraped data, do not publish derived datasets, and do not make this
  repo's `data/` directory public. Club logos/crests are never
  downloaded.
- **No player-level personal data is scraped.** v1 is match-level only
  (teams, scores, dates, venue name) — no player names, referees, or
  staff. Match-detail pages (which carry that data, including for
  minors in the youth brackets) are out of scope by design, not by
  omission.
- **`data/` is gitignored.** Raw HTML cache, normalized JSON, logs, and
  reports all live under `data/` and are never committed. See `.gitignore`.

---

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) (Python env/dependency manager)
- [Docker](https://www.docker.com/) + Docker Compose (for the local Neo4j instance)
- Python 3.13 is pinned via `.python-version`; `uv` will fetch it automatically.

## Setup

```bash
cd dk-football-results-graph
cp .env.example .env
# Edit .env and set DBU_CONTACT_EMAIL to a real contact address —
# this is embedded in the User-Agent sent to dbu.dk (required, no default).

uv sync                # installs dependencies into .venv
uv run dkfr --help     # lists every pipeline subcommand
```

## Running the graph database

```bash
docker compose up -d
# Neo4j Browser: http://localhost:7474  (user/pass from .env, default neo4j/changeme12345)
# Bolt:          bolt://localhost:7687
```

## Pipeline stages

Each stage is independently runnable and reads only the previous stage's
durable artefact — you can re-run any stage without re-running the ones
before it (as long as its input artefact already exists).

| Stage | Command | Reads | Writes | Network? |
|---|---|---|---|---|
| 1. Fetch | `uv run dkfr fetch --all` | `manifest/puljer.yaml` | `data/cache/pulje/<id>/<view>.html` + `.meta.json` | Yes — polite, cached, ≥2s between requests |
| 2. Parse | `uv run dkfr parse` | `data/cache/` | `data/normalized/{matches.jsonl,puljer.json,teams.json,clubs.json,venues.json}` | No |
| 3. Load | `uv run dkfr load` | `data/normalized/` | Neo4j (local Docker) | No (Bolt only) |
| 4. Derive | `uv run dkfr derive` | Neo4j | Neo4j (`PLAYED_AGAINST`) | No |
| 5. Validate | `uv run dkfr validate` | Neo4j + `data/normalized/` | `data/reports/{validation,standings-reconciliation}.json` | No |

Convenience: `uv run dkfr all` runs stages 1–5 in order.

Other utilities:

```bash
uv run dkfr manifest verify   # confirm every manifest pulje resolves to a live page
                               # with a matching title (AC1)
uv run dkfr names review      # print/regenerate the unresolved team-name report
uv run dkfr query u01-opponents --param teamId=<id>   # run a checked-in Cypher query
```

## The manifest — `manifest/puljer.yaml`

This is the hand-curated, checked-in list of DBU `pulje` (pool) IDs that
defines the scrape's scope. It is the primary discovery mechanism (there
is no robots-permitted way to programmatically enumerate puljer — see
spec F5/F11/C5). Two top-level sections:

- `competitions:` — declared once per competition (name, bracket, gender,
  ageBracket, tier, administrator).
- `puljer:` — one entry per pulje (puljeId, competitionId reference,
  phase, groupLabel, pointsCarryOver, expectedTeams, expectedMatches,
  note). `expectedMatches` is nullable — filled only where a source
  (typically Wikipedia's season article) documents the format.

Run `uv run dkfr manifest verify` after editing to confirm every entry
still resolves to a live pulje page whose title matches the declared
competition/phase/season.

Team-name normalization is driven by `manifest/aliases.yaml` (raw name ->
canonical name, optional clubId/dbuTeamId) and club grouping by
`manifest/clubs.yaml` (exceptions to the default slug-based grouping
rule). Both are hand-curated based on the `data/reports/unresolved-names.json`
report — never auto-resolved.

## Development

```bash
uv run pytest          # unit tests (fast, no network, no live DB required)
uv run pytest -m ""    # include live_db / live_cache marked tests too, if you have
                        # a running Neo4j / warm cache
uv run ruff check .
```

Test fixtures under `tests/fixtures/html/` are **synthetic, hand-authored**
HTML reproducing DBU's observed table structures — never real scraped
pages, to keep the test suite committable regardless of repo visibility.

## Source and legal constraints (summary)

- Source: `https://www.dbu.dk/resultater/` — server-rendered pulje pages,
  the unified results system for every national DBU competition.
- `robots.txt` disallows `/resultater/kampsoegAdvanceret/` and
  `/turneringer_og_resultater/resultatsoegning/`; the scraper never
  requests either. `robots.txt` is parsed programmatically, not just
  hard-coded.
- DBU's terms of use forbid reproducing/sharing protected content and
  forbid use of logos/trademarks without written permission. Private,
  personal analysis is the stated purpose of this project; publishing
  the scraped dataset is explicitly out of scope and not permitted.
- No official API exists that covers this scope (see spec F7/F8) — this
  project scrapes public HTML pages, politely, as the only viable path.

---

## Graph database

`docs/schema/model.md` is the human-facing schema reference — label/
relationship catalog, property tables, enum values, post-load invariants,
and known limitations. It must stay in sync with `cypher/schema.cypher`,
`cypher/validation.cypher`, `cypher/derive.cypher`, and `queries/*.cypher`.

Neo4j Browser at http://localhost:7474 is the easiest way to explore the
graph interactively once it's loaded; the `queries/*.cypher` files can be
pasted directly into it, or run via `dkfr query <name> --param k=v`.

## Implementation status

All 16 tasks in the design's breakdown (T1-T16) are implemented and
verified against a real scrape of the full 31-pulje manifest and a real
local Docker Neo4j — see the developer's final report for the complete,
task-by-task account of what was verified and how, and for the honestly-
flagged known limitations (a handful of standings-reconciliation
discrepancies with documented, evidenced explanations — see
`docs/specs/dk-results-scraper/discovery-notes.md`'s T14 addendum).

- **Phase A (foundation):** done. Manifest has 31 real, verified pulje IDs
  (`dkfr manifest verify`: 31/31 OK).
- **Phase B (extraction):** done. Full parse of the real manifest: 2065
  matches, 143 teams, 101 clubs, 139 venues, 256 standing rows.
- **Phase C (graph):** done. Full load + validate + derive against the
  real dataset: all post-load invariants pass, all graph/JSON counts
  reconcile, all 11 query-set use cases (U1-U11) verified against real
  data.
- **Phase D (validation/hardening):** done. Standings reconciliation
  (AC8) and an independent-source spot-check (AC9) both completed with
  real, documented results.
