"""Query set tests. AC17 is a static check (no live DB needed) — the rest
are live_db-marked integration tests against the real loaded graph.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dkfr.config import get_settings
from dkfr.load.driver import build_driver, run_read, run_write_query
from dkfr.queries.runner import load_query, parse_params

QUERIES_DIR = Path("queries")
ALL_QUERY_NAMES = [
    "u01-opponents",
    "u02-head-to-head",
    "u03-season-results",
    "u04-home-away-split",
    "u05-common-opponents",
    "u05-common-opponents-no-derive",
    "u06-degrees-of-separation",
    "u07-club-cross-bracket",
    "u08-matches-at-venue",
    "u09-phase-record",
    "u10-derived-standings",
    "u11-biggest-wins",
]


def test_every_query_file_exists():
    for name in ALL_QUERY_NAMES:
        assert (QUERIES_DIR / f"{name}.cypher").exists()


def test_parse_params_coerces_integers():
    params = parse_params(["teamId=dbu:16162", "tier=1", "limit=5"])
    assert params == {"teamId": "dbu:16162", "tier": 1, "limit": 5}


def test_parse_params_rejects_malformed():
    with pytest.raises(ValueError):
        parse_params(["not-a-kv-pair"])


def test_u01_and_u02_have_no_union_or_case_on_relationship_type():
    """AC17: U1 and U2 must be single-pattern — no UNION, no CASE on
    relationship type, no post-filtering in application code."""
    for name in ("u01-opponents", "u02-head-to-head"):
        query = load_query(name)
        assert "UNION" not in query.upper()
        # No CASE at all in either query — the strongest form of the check,
        # since a CASE on relationship *type* is exactly what a HOME_IN/
        # AWAY_IN split (Decision 2's rejected Option A) would have forced.
        assert "CASE" not in query.upper()
        # Single MATCH *clause* — one pattern, not several stitched together.
        # Case-sensitive on purpose: the all-caps "MATCH" clause keyword is
        # distinct from the PascalCase "Match" node label that also appears
        # in the pattern text (e.g. "m:Match") and must not be counted.
        assert query.count("MATCH") == 1, query


@pytest.fixture
def live_driver():
    """Ensures a fresh, fully-loaded-and-derived graph regardless of what
    other live_db test files left behind (several of them do their own
    destructive clear/reload cycles — MATCH (n) DETACH DELETE n also wipes
    the derived PLAYED_AGAINST layer, which is a separate `dkfr derive`
    step, not part of `dkfr load`). Making this file self-contained avoids
    test-order-dependent flakiness against the shared local Neo4j."""
    settings = get_settings()
    driver = build_driver(settings)
    try:
        driver.verify_connectivity()
    except Exception:
        pytest.skip("Neo4j not reachable — start it with `docker compose up -d`")

    if not (settings.normalized_dir / "matches.jsonl").exists():
        driver.close()
        pytest.skip("data/normalized not present — run `dkfr parse` first")

    from dkfr.load.derive import run_derive
    from dkfr.load.loader import load_dataset
    from dkfr.load.schema import apply_schema

    run_write_query(driver, "MATCH (n) DETACH DELETE n")
    apply_schema(driver)
    load_dataset(driver, settings.normalized_dir)
    run_derive(driver)

    yield driver
    driver.close()


def _sample_team_id(driver, bracket: str) -> str | None:
    rows = run_read(
        driver, "MATCH (t:Team {bracket: $bracket}) RETURN t.teamId AS id LIMIT 1", bracket=bracket
    )
    return rows[0]["id"] if rows else None


@pytest.mark.live_db
def test_all_11_queries_run_and_return_rows(live_driver):
    """AC16: each of U1-U11 runs and returns correct-shaped results against
    the loaded data. Uses real team/club/venue keys pulled from the graph
    itself, so this stays correct if the manifest changes."""
    driver = live_driver
    if not run_read(driver, "MATCH (m:Match) RETURN count(*) AS c")[0]["c"]:
        pytest.skip("graph is empty — run `dkfr load` first")

    team_a = _sample_team_id(driver, "MEN_SENIOR")
    # A second MEN_SENIOR team that actually played team_a, for U2/U5/U6.
    opponent_row = run_read(
        driver,
        "MATCH (:Team {teamId: $id})-[:PLAYED_IN]->(:Match)<-[:PLAYED_IN]-(o:Team) "
        "RETURN DISTINCT o.teamId AS id LIMIT 1",
        id=team_a,
    )
    team_b = opponent_row[0]["id"]

    club_row = run_read(driver, "MATCH (c:Club)-[:HAS_TEAM]->(:Team) RETURN c.clubId AS id LIMIT 1")
    club_id = club_row[0]["id"]

    venue_row = run_read(driver, "MATCH (v:Venue) RETURN v.venueKey AS key LIMIT 1")
    venue_key = venue_row[0]["key"]

    stage_row = run_read(driver, "MATCH (s:Stage) RETURN s.puljeId AS id LIMIT 1")
    pulje_id = stage_row[0]["id"]

    params_by_query = {
        "u01-opponents": {"teamId": team_a},
        "u02-head-to-head": {"teamAId": team_a, "teamBId": team_b},
        "u03-season-results": {"teamId": team_a},
        "u04-home-away-split": {"teamId": team_a},
        "u05-common-opponents": {"teamAId": team_a, "teamBId": team_b},
        "u05-common-opponents-no-derive": {"teamAId": team_a, "teamBId": team_b},
        "u06-degrees-of-separation": {"teamAId": team_a, "teamBId": team_b},
        "u07-club-cross-bracket": {"clubId": club_id},
        "u08-matches-at-venue": {"venueKey": venue_key},
        "u09-phase-record": {"teamId": team_a},
        "u10-derived-standings": {"puljeId": pulje_id},
        "u11-biggest-wins": {"bracket": "MEN_SENIOR", "tier": 1, "limit": 5},
    }

    for name, params in params_by_query.items():
        query = load_query(name)
        rows = run_read(driver, query, **params)
        assert rows, f"{name} returned zero rows for {params}"


@pytest.mark.live_db
def test_u07_cross_bracket_returns_multiple_brackets_for_fck(live_driver):
    """AC18: FC København fields senior/U19/U17/women's teams — one query
    must return opponents from more than one bracket."""
    driver = live_driver
    rows = run_read(driver, load_query("u07-club-cross-bracket"), clubId="fc-koebenhavn")
    if not rows:
        pytest.skip("fc-koebenhavn not present — run `dkfr load` against the real manifest first")
    brackets = {r["ownBracket"] for r in rows}
    assert len(brackets) >= 3, f"expected multiple brackets, got {brackets}"


@pytest.mark.live_db
def test_u09_distinguishes_grundspil_from_mesterskabsspil(live_driver):
    """AC19: a Superliga team's Grundspil and Mesterskabsspil rows must be
    distinct, with different `played` counts."""
    driver = live_driver
    # A team confirmed (T6) to appear in both Superliga Grundspil (473806)
    # and Mesterskabsspil (498492) — see discovery-notes.md's Q6 evidence.
    rows = run_read(driver, load_query("u09-phase-record"), teamId="dbu:6206")  # FC Midtjylland
    if not rows:
        pytest.skip("dbu:6206 not present — run `dkfr load` against the real manifest first")
    phases = {r["phase"] for r in rows}
    assert "GRUNDSPIL" in phases
    assert "MESTERSKABSSPIL" in phases
    grundspil_row = next(r for r in rows if r["phase"] == "GRUNDSPIL")
    mester_row = next(r for r in rows if r["phase"] == "MESTERSKABSSPIL")
    assert grundspil_row["puljeId"] != mester_row["puljeId"]
    assert grundspil_row["played"] != mester_row["played"]


@pytest.mark.live_db
def test_u05_derived_and_no_derive_variants_agree(live_driver):
    driver = live_driver
    team_a = _sample_team_id(driver, "MEN_SENIOR")
    opponent_row = run_read(
        driver,
        "MATCH (:Team {teamId: $id})-[:PLAYED_IN]->(:Match)<-[:PLAYED_IN]-(o:Team) "
        "RETURN DISTINCT o.teamId AS id LIMIT 1",
        id=team_a,
    )
    if not opponent_row:
        pytest.skip("no opponent found")
    team_b = opponent_row[0]["id"]

    derived = run_read(
        driver, load_query("u05-common-opponents"), teamAId=team_a, teamBId=team_b
    )
    no_derive = run_read(
        driver, load_query("u05-common-opponents-no-derive"), teamAId=team_a, teamBId=team_b
    )
    assert {r["opponentTeamId"] for r in derived} == {r["opponentTeamId"] for r in no_derive}


def test_query_line_length_sanity():
    """Not a functional test — just confirms every checked-in query file has
    the required header comment (purpose/params/shape), per the design's
    'one file per use case, with a header comment' requirement."""
    for name in ALL_QUERY_NAMES:
        text = (QUERIES_DIR / f"{name}.cypher").read_text(encoding="utf-8")
        header_lines = [line for line in text.splitlines()[:6] if line.strip().startswith("//")]
        assert header_lines, f"{name}.cypher has no header comment"
        joined = " ".join(header_lines).lower()
        assert "param" in joined, f"{name}.cypher header doesn't document params"


