"""Ordered idempotent MERGE load: Competition -> Season -> Stage -> Club ->
Team -> Venue -> Match -> PLAYED_IN -> PARTICIPATED_IN (design T10).

Reads only data/normalized/* — this stage never touches the scraper or the
HTML cache (R3.2: "re-running the loader must not require re-running the
scraper"). MERGE on every business key makes a repeat run idempotent (G6/
AC14): same JSON in, same node/relationship counts out, no duplicates.
"""

from __future__ import annotations

import json
from pathlib import Path

from dkfr.load.driver import run_unwind_write
from dkfr.vocab import Outcome

SEASON_LABEL = "2025/26"
SEASON_CODE = "2026"


class LoadIntegrityError(RuntimeError):
    """A pre-write invariant (home != away, etc.) was violated by the input
    JSON — refuses to load rather than silently writing a bad graph."""


def _read_json(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _season_id(competition_id: str) -> str:
    return f"{competition_id}:2025-26"


def _outcome_and_points(goals_for: int | None, goals_against: int | None) -> tuple[str, int]:
    if goals_for is None or goals_against is None:
        return Outcome.UNKNOWN.value, 0
    if goals_for > goals_against:
        return Outcome.WIN.value, 3
    if goals_for < goals_against:
        return Outcome.LOSS.value, 0
    return Outcome.DRAW.value, 1


# --- Cypher templates, one per entity/relationship type ---

_COMPETITION_CYPHER = """
UNWIND $rows AS row
MERGE (c:Competition {competitionId: row.competitionId})
SET c.name = row.name, c.bracket = row.bracket, c.gender = row.gender,
    c.ageBracket = row.ageBracket, c.tier = row.tier, c.administrator = row.administrator
"""

_SEASON_CYPHER = """
UNWIND $rows AS row
MERGE (s:Season {seasonId: row.seasonId})
SET s.label = row.label, s.seasonCode = row.seasonCode
WITH s, row
MATCH (c:Competition {competitionId: row.competitionId})
MERGE (c)-[:HAS_SEASON]->(s)
"""

_STAGE_CYPHER = """
UNWIND $rows AS row
MERGE (st:Stage {puljeId: row.puljeId})
SET st.name = row.puljeName, st.phase = row.phase, st.groupLabel = row.groupLabel,
    st.competitionId = row.competitionId, st.season = row.season, st.tier = row.tier,
    st.bracket = row.bracket, st.administrator = row.administrator,
    st.pointsCarryOver = row.pointsCarryOver, st.teamCount = row.teamCount,
    st.matchCount = row.matchCount, st.sourceUrl = row.sourceUrl, st.fetchedAt = row.fetchedAt
WITH st, row
MATCH (se:Season {seasonId: row.seasonId})
MERGE (st)-[:IN_SEASON]->(se)
"""

_CLUB_CYPHER = """
UNWIND $rows AS row
MERGE (c:Club {clubId: row.clubId})
SET c.name = row.name
"""

_TEAM_CYPHER = """
UNWIND $rows AS row
MERGE (t:Team {teamId: row.teamId})
SET t.name = row.name, t.bracket = row.bracket, t.gender = row.gender,
    t.ageBracket = row.ageBracket, t.squadIndex = row.squadIndex,
    t.dbuTeamId = row.dbuTeamId, t.sourceNames = row.sourceNames
WITH t, row
MATCH (c:Club {clubId: row.clubId})
MERGE (c)-[:HAS_TEAM]->(t)
"""

_VENUE_CYPHER = """
UNWIND $rows AS row
MERGE (v:Venue {venueKey: row.venueKey})
SET v.name = row.name
"""

_MATCH_CYPHER = """
UNWIND $rows AS row
MERGE (m:Match {matchKey: row.matchKey})
SET m.matchNumber = row.matchNumber,
    m.date = date(row.date),
    m.kickoffAt = CASE WHEN row.kickoffAt IS NOT NULL THEN datetime(row.kickoffAt) ELSE NULL END,
    m.kickoffTimeLocal = row.kickoffTimeLocal,
    m.status = row.status,
    m.totalGoals = row.totalGoals,
    m.goalMargin = row.goalMargin,
    m.hasPenalties = row.hasPenalties,
    m.puljeId = row.puljeId,
    m.competitionId = row.competitionId,
    m.phase = row.phase,
    m.tier = row.tier,
    m.bracket = row.bracket,
    m.gender = row.gender,
    m.ageBracket = row.ageBracket,
    m.season = row.season,
    m.sourceUrl = row.sourceUrl,
    m.fetchedAt = row.fetchedAt,
    m.scraperVersion = row.scraperVersion
WITH m, row
MATCH (st:Stage {puljeId: row.puljeId})
MERGE (m)-[:IN_STAGE]->(st)
WITH m, row
CALL (m, row) {
    WITH m, row WHERE row.venueKey IS NOT NULL
    MATCH (v:Venue {venueKey: row.venueKey})
    MERGE (m)-[:PLAYED_AT]->(v)
}
"""

_PLAYED_IN_CYPHER = """
UNWIND $rows AS row
MATCH (t:Team {teamId: row.teamId})
MATCH (m:Match {matchKey: row.matchKey})
MERGE (t)-[p:PLAYED_IN {side: row.side}]->(m)
SET p.goalsFor = row.goalsFor, p.goalsAgainst = row.goalsAgainst,
    p.outcome = row.outcome, p.points = row.points,
    p.penaltyGoalsFor = row.penaltyGoalsFor, p.penaltyGoalsAgainst = row.penaltyGoalsAgainst
"""

_PARTICIPATED_IN_CYPHER = """
UNWIND $rows AS row
MATCH (t:Team {teamId: row.teamId})
MATCH (st:Stage {puljeId: row.puljeId})
MERGE (t)-[r:PARTICIPATED_IN]->(st)
SET r.rank = row.rank, r.played = row.played, r.won = row.won, r.drawn = row.drawn,
    r.lost = row.lost, r.goalsFor = row.goalsFor, r.goalsAgainst = row.goalsAgainst,
    r.goalDifference = row.goalDifference, r.points = row.points
"""


def load_dataset(driver, normalized_dir: Path) -> dict[str, int]:
    competitions = _read_json(normalized_dir / "competitions.json")
    puljer = _read_json(normalized_dir / "puljer.json")
    clubs = _read_json(normalized_dir / "clubs.json")
    teams = _read_json(normalized_dir / "teams.json")
    venues = _read_json(normalized_dir / "venues.json")
    matches = _read_jsonl(normalized_dir / "matches.jsonl")
    standings = _read_jsonl(normalized_dir / "standings.jsonl")

    # --- pre-write invariant checks (C10: loader-enforced, schema can't) ---
    for m in matches:
        if m["homeTeamId"] == m["awayTeamId"]:
            raise LoadIntegrityError(
                f"match {m['matchKey']} has identical home and away team "
                f"{m['homeTeamId']!r} — refusing to load"
            )

    seasons = {_season_id(c["competitionId"]): c["competitionId"] for c in competitions}
    season_rows = [
        {"seasonId": sid, "competitionId": cid, "label": SEASON_LABEL, "seasonCode": SEASON_CODE}
        for sid, cid in seasons.items()
    ]

    stage_rows = [
        {**p, "season": SEASON_LABEL, "seasonId": _season_id(p["competitionId"])} for p in puljer
    ]

    match_rows = matches  # already flat, keys match the Cypher template 1:1

    played_in_rows = []
    for m in matches:
        home_outcome, home_points = _outcome_and_points(m["homeGoals"], m["awayGoals"])
        away_outcome, away_points = _outcome_and_points(m["awayGoals"], m["homeGoals"])
        played_in_rows.append(
            {
                "matchKey": m["matchKey"],
                "teamId": m["homeTeamId"],
                "side": "HOME",
                "goalsFor": m["homeGoals"],
                "goalsAgainst": m["awayGoals"],
                "outcome": home_outcome,
                "points": home_points,
                "penaltyGoalsFor": m["penaltyHomeGoals"],
                "penaltyGoalsAgainst": m["penaltyAwayGoals"],
            }
        )
        played_in_rows.append(
            {
                "matchKey": m["matchKey"],
                "teamId": m["awayTeamId"],
                "side": "AWAY",
                "goalsFor": m["awayGoals"],
                "goalsAgainst": m["homeGoals"],
                "outcome": away_outcome,
                "points": away_points,
                "penaltyGoalsFor": m["penaltyAwayGoals"],
                "penaltyGoalsAgainst": m["penaltyHomeGoals"],
            }
        )

    stats: dict[str, int] = {}
    stats["Competition"] = run_unwind_write(driver, _COMPETITION_CYPHER, competitions)
    stats["Season"] = run_unwind_write(driver, _SEASON_CYPHER, season_rows)
    stats["Stage"] = run_unwind_write(driver, _STAGE_CYPHER, stage_rows)
    stats["Club"] = run_unwind_write(driver, _CLUB_CYPHER, clubs)
    stats["Team"] = run_unwind_write(driver, _TEAM_CYPHER, teams)
    stats["Venue"] = run_unwind_write(driver, _VENUE_CYPHER, venues)
    stats["Match"] = run_unwind_write(driver, _MATCH_CYPHER, match_rows)
    stats["PLAYED_IN"] = run_unwind_write(driver, _PLAYED_IN_CYPHER, played_in_rows)
    stats["PARTICIPATED_IN"] = run_unwind_write(driver, _PARTICIPATED_IN_CYPHER, standings)

    return stats
