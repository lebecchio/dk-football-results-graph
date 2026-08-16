# dk-football-results-graph

This repo follows the analyst → architect → developer → reviewer pipeline
defined globally in `~/.claude/CLAUDE.md` and `~/.claude/agents/` — no
project-specific setup is required for that part, it's already active
here. Read `~/.claude/CLAUDE.md` for the methodology. This file covers
only what's specific to this repo.

## What's specific here

- **Deliverable:** a scraper/ETL pipeline that collects all match results
  for the Danish football (soccer) 2025/26 season across the
  nationally-administered tiers on dbu.dk (Superliga, 1st Division, 2nd
  Division, Denmark Series), across all 6 age/gender brackets (men's and
  women's senior, U19, U17), normalizes them into structured data (e.g.
  JSON), and loads them into a Neo4j graph database for traversal queries
  (which teams a given team has played, with what results). Regional/
  lower-tier amateur football (below Denmark Series, served by the 6
  separate DBU regional-union sites) is out of scope for this pass —
  flagged in the stage-0 feasibility check as fragmented across
  differently-structured sites with degrading data quality, a candidate
  for a future phase.
- **Model pin:** none by default. Add a `.claude/settings.json` with
  `{"model": "opus"}` (or another tier) if this repo's implementation
  work should always run on a specific model regardless of your personal
  `/model` default — see skill-factory's `.claude/settings.json` for an
  example.
- **Specs and designs:** as in the global convention, save these under
  `docs/specs/<feature>/spec.md` (and `design.md`, when the architect
  runs) before implementation starts. The `docs/specs/` folder here is
  currently empty — it fills up as work starts.

## Getting started

Open this repo in Claude Code and start new work with:

> Use the analyst to spec out [your feature], then have the architect turn
> that into a design, then let's build it.

For quick, low-complexity data cleanup or extraction tasks (not part of
the pipeline), invoke the **extractor** subagent (Haiku) directly instead.

The global pipeline description covers routing (when the architect gets
skipped, when the pipeline gets skipped entirely for trivial changes) and
the developer/reviewer handoff — see `~/.claude/CLAUDE.md`.
