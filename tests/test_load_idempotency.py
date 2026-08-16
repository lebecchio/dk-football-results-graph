"""Loader tests. Pure-logic pieces run offline; the idempotency/reconciliation
checks (AC14/AC15) require a live Neo4j and are marked `live_db` — they run
against the local Docker instance (docker-compose.yml) when available and
skip cleanly otherwise.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dkfr.config import get_settings
from dkfr.load.driver import build_driver, run_read, run_write_query
from dkfr.load.loader import LoadIntegrityError, _outcome_and_points, load_dataset
from dkfr.load.schema import apply_schema


def test_outcome_and_points_win_draw_loss():
    assert _outcome_and_points(3, 1) == ("WIN", 3)
    assert _outcome_and_points(1, 1) == ("DRAW", 1)
    assert _outcome_and_points(0, 2) == ("LOSS", 0)
    assert _outcome_and_points(None, None) == ("UNKNOWN", 0)


def test_load_rejects_match_with_identical_home_and_away_team(tmp_path):
    _write_minimal_normalized_dir(tmp_path, corrupt_home_eq_away=True)
    with pytest.raises(LoadIntegrityError):
        load_dataset(_FakeDriver(), tmp_path)


def _write_minimal_normalized_dir(dir_: Path, *, corrupt_home_eq_away: bool = False) -> None:
    (dir_ / "competitions.json").write_text(json.dumps([]))
    (dir_ / "puljer.json").write_text(json.dumps([]))
    (dir_ / "clubs.json").write_text(json.dumps([]))
    (dir_ / "teams.json").write_text(json.dumps([]))
    (dir_ / "venues.json").write_text(json.dumps([]))
    (dir_ / "standings.jsonl").write_text("")
    home_id = "dbu:1" if not corrupt_home_eq_away else "dbu:1"
    away_id = "dbu:2" if not corrupt_home_eq_away else "dbu:1"
    match = {
        "matchKey": "1:1",
        "homeTeamId": home_id,
        "awayTeamId": away_id,
        "homeGoals": 1,
        "awayGoals": 0,
        "penaltyHomeGoals": None,
        "penaltyAwayGoals": None,
    }
    (dir_ / "matches.jsonl").write_text(json.dumps(match) + "\n")


class _FakeDriver:
    """Never actually used when the integrity check raises before any
    session is opened — exists only so load_dataset can be called without a
    live Neo4j for this one offline test."""


@pytest.mark.live_db
def test_full_load_is_idempotent_against_the_real_manifest():
    settings = get_settings()
    normalized_dir = settings.normalized_dir
    if not (normalized_dir / "matches.jsonl").exists():
        pytest.skip("data/normalized not present — run `dkfr parse` first")

    driver = build_driver(settings)
    try:
        driver.verify_connectivity()
    except Exception:
        pytest.skip("Neo4j not reachable — start it with `docker compose up -d`")

    try:
        run_write_query(driver, "MATCH (n) DETACH DELETE n")
        apply_schema(driver)

        load_dataset(driver, normalized_dir)
        counts_1 = _counts(driver)

        load_dataset(driver, normalized_dir)
        counts_2 = _counts(driver)

        assert counts_1 == counts_2, "re-loading changed node/relationship counts (AC14)"

        matches_lines = (normalized_dir / "matches.jsonl").read_text().splitlines()
        matches_jsonl_count = sum(1 for line in matches_lines if line.strip())
        assert counts_1["Match"] == matches_jsonl_count, "AC15: graph vs JSON match count mismatch"
    finally:
        driver.close()


def _counts(driver) -> dict[str, int]:
    node_rows = run_read(driver, "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS cnt")
    rel_rows = run_read(driver, "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS cnt")
    result = {row["label"]: row["cnt"] for row in node_rows}
    result.update({row["type"]: row["cnt"] for row in rel_rows})
    return result
