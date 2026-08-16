"""Standings reconciliation (U10 vs PARTICIPATED_IN) — spec AC8, design T14.

Compares the derived standings (reconstructed from PLAYED_IN, same logic as
queries/u10-derived-standings.cypher) against the scraped stillingFuld
table (stored on PARTICIPATED_IN edges) for a given pulje.

CORRECTION TO THE DESIGN'S R-3 ASSUMPTION, found empirically running this
reconciliation for real: R-3 assumed only `points` carries over into
playoff-phase puljer (Mesterskabsspil/Oprykningsspil/Kvalifikationsspil),
with played/GF/GA staying phase-scoped ("T14 compares only match-derived
columns... for those puljer"). The real scraped data shows DBU's
stillingFuld for those phases displays the team's CUMULATIVE season total
— e.g. a Superliga Mesterskabsspil team's `played` on that page is
32 (=22 Grundspil rounds + 10 Mesterskabsspil rounds), not 10. So for
`pointsCarryOver=True` puljer, EVERY column is on a different basis than
this pulje's own matches, not just points — a per-column comparison isn't
meaningful at all, so those puljer are reported with `compared=False` and
an explanatory note rather than an attempted (and inevitably wrong) column
check. This matches the design's actual intent ("carry-over stages are
reported separately with an explanation rather than as failures") more
precisely than the original R-3 text described.

A second, smaller effect found on genuinely non-carry-over puljer: walkover
matches (HHT/UHT — see discovery-notes.md's T6 addendum) have no
goalsFor/goalsAgainst, so the Python-side derived aggregation (which sums
`WHERE p.goalsFor IS NOT NULL`) excludes them entirely, while DBU's own
scraped standings evidently DOES count a walkover as played and awards
points for it. Puljer containing a walkover will show a small, explainable
mismatch for this reason — noted per-pulje in the report, not treated as a
silent pass.
"""

from __future__ import annotations

from pydantic import BaseModel

from dkfr.load.driver import run_read

_DERIVED_QUERY = """
MATCH (t:Team)-[p:PLAYED_IN]->(m:Match)-[:IN_STAGE]->(s:Stage {puljeId: $puljeId})
WHERE p.goalsFor IS NOT NULL
RETURN
  t.teamId AS teamId,
  count(*) AS played,
  sum(CASE WHEN p.outcome = 'WIN' THEN 1 ELSE 0 END) AS won,
  sum(CASE WHEN p.outcome = 'DRAW' THEN 1 ELSE 0 END) AS drawn,
  sum(CASE WHEN p.outcome = 'LOSS' THEN 1 ELSE 0 END) AS lost,
  sum(p.goalsFor) AS goalsFor,
  sum(p.goalsAgainst) AS goalsAgainst,
  sum(p.points) AS points
"""

_SCRAPED_QUERY = """
MATCH (t:Team)-[r:PARTICIPATED_IN]->(s:Stage {puljeId: $puljeId})
RETURN
  t.teamId AS teamId,
  r.played AS played,
  r.won AS won,
  r.drawn AS drawn,
  r.lost AS lost,
  r.goalsFor AS goalsFor,
  r.goalsAgainst AS goalsAgainst,
  r.points AS points
"""

COMPARED_COLUMNS = ("played", "won", "drawn", "lost", "goalsFor", "goalsAgainst", "points")


class TeamMismatch(BaseModel):
    teamId: str
    column: str
    derived: int | None
    scraped: int | None


class PuljeReconciliation(BaseModel):
    puljeId: int
    pointsCarryOver: bool
    compared: bool  # False for carry-over puljer — see module docstring
    teamsCompared: int
    mismatches: list[TeamMismatch]
    passed: bool
    note: str | None = None


def reconcile_pulje(driver, pulje_id: int, points_carry_over: bool) -> PuljeReconciliation:
    scraped_rows = {r["teamId"]: r for r in run_read(driver, _SCRAPED_QUERY, puljeId=pulje_id)}

    if points_carry_over:
        # Every column is cumulative-season-to-date on DBU's own page for
        # these puljer, not phase-scoped — a column comparison against this
        # pulje's own (phase-scoped) matches isn't meaningful. See module
        # docstring for the empirical finding that corrected this from the
        # design's original "points only" assumption.
        return PuljeReconciliation(
            puljeId=pulje_id,
            pointsCarryOver=True,
            compared=False,
            teamsCompared=len(scraped_rows),
            mismatches=[],
            passed=True,
            note=(
                "pointsCarryOver=true: DBU's stillingFuld for this pulje shows the "
                "cumulative season-to-date total (all columns), not this pulje's own "
                "phase-scoped record — column-by-column comparison against this "
                "pulje's own matches is not meaningful, so it was skipped rather than "
                "reported as a false failure."
            ),
        )

    derived_rows = {r["teamId"]: r for r in run_read(driver, _DERIVED_QUERY, puljeId=pulje_id)}

    mismatches: list[TeamMismatch] = []
    for team_id, scraped in scraped_rows.items():
        derived = derived_rows.get(team_id)
        for col in COMPARED_COLUMNS:
            derived_val = derived[col] if derived else None
            scraped_val = scraped[col]
            if derived_val != scraped_val:
                mismatches.append(
                    TeamMismatch(
                        teamId=team_id, column=col, derived=derived_val, scraped=scraped_val
                    )
                )

    note = None
    if mismatches:
        cols_hit = {m.column for m in mismatches}
        if cols_hit == {"points"}:
            # Empirically confirmed (T14) on U19 Drenge Ligaen (pulje 473921):
            # every mismatch is a small points-only deficit that correlates
            # exactly with the team's count of WON penalty shootouts. DBU's
            # points system for at least this competition evidently awards a
            # bonus point for a penalty-shootout win beyond the standard
            # 1-point draw (a common "no true draws" scoring rule) — the
            # loader's points formula (3/1/0 by W/D/L only) doesn't model
            # this. Not corrected here: the exact bonus scheme isn't
            # confirmed across every bracket, and the design's points field
            # is documented as W/D/L-derived only (Decision 2) — flagging
            # this as a known, explained limitation rather than guessing at
            # a scheme and risking a worse silent error.
            note = (
                "All mismatches are points-only (played/won/drawn/lost/goals all "
                "match exactly). One confirmed cause on pulje 473921: DBU awards a "
                "bonus point for winning a penalty shootout beyond the standard "
                "1-point draw, which this pipeline's points formula (3/1/0 by "
                "W/D/L only) doesn't model. NOT confirmed as the cause for every "
                "pulje with this pattern — e.g. some affected puljer have zero "
                "penalty-shootout matches at all, so an administrative points "
                "adjustment (points deduction, etc. — invisible to a match-results "
                "scraper by construction) is also plausible. Flagged for human "
                "review, not auto-corrected or auto-explained away."
            )
        else:
            note = (
                "Mismatches touch played/won/drawn/lost/goals, not just points — "
                "most likely a walkover match (HHT/UHT, see discovery-notes.md T6 "
                "addendum): the derived aggregation excludes matches with no "
                "goalsFor/goalsAgainst, while DBU's own standings evidently count "
                "a walkover as played. Verify per pulje; not auto-explained here."
            )

    return PuljeReconciliation(
        puljeId=pulje_id,
        pointsCarryOver=False,
        compared=True,
        teamsCompared=len(scraped_rows),
        mismatches=mismatches,
        passed=len(mismatches) == 0,
        note=note,
    )


def reconcile_all(driver, manifest) -> list[PuljeReconciliation]:
    results = []
    for pulje in manifest.puljer:
        result = reconcile_pulje(driver, pulje.puljeId, pulje.pointsCarryOver)
        if result.teamsCompared > 0:  # skip puljer with no stillingFuld (e.g. 503898)
            results.append(result)
    return results
