"""dkfr.load.derive — PLAYED_AGAINST rebuild tests (marked live_db)."""

from __future__ import annotations

import json

import pytest

from dkfr.config import get_settings
from dkfr.load.derive import run_derive
from dkfr.load.driver import build_driver, run_read, run_write_query
from dkfr.load.loader import load_dataset
from dkfr.load.schema import apply_schema


@pytest.mark.live_db
def test_played_against_count_matches_distinct_team_pairs_and_is_idempotent():
    settings = get_settings()
    matches_path = settings.normalized_dir / "matches.jsonl"
    if not matches_path.exists():
        pytest.skip("data/normalized not present — run `dkfr parse` first")

    driver = build_driver(settings)
    try:
        driver.verify_connectivity()
    except Exception:
        pytest.skip("Neo4j not reachable — start it with `docker compose up -d`")

    try:
        run_write_query(driver, "MATCH (n) DETACH DELETE n")
        apply_schema(driver)
        load_dataset(driver, settings.normalized_dir)

        pairs = set()
        for line in matches_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            m = json.loads(line)
            a, b = sorted([m["homeTeamId"], m["awayTeamId"]])
            pairs.add((a, b))

        count_query = "MATCH ()-[r:PLAYED_AGAINST]->() RETURN count(*) AS cnt"

        run_derive(driver)
        count_1 = run_read(driver, count_query)[0]["cnt"]
        assert count_1 == len(pairs)

        run_derive(driver)
        count_2 = run_read(driver, count_query)[0]["cnt"]
        assert count_2 == count_1, "re-running derive changed the PLAYED_AGAINST count"
    finally:
        driver.close()
