"""dkfr.load.validate tests — the parser offline, the live checks against
the local Docker Neo4j (marked live_db, skips cleanly without one)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dkfr.config import get_settings
from dkfr.load.driver import build_driver, run_write_query
from dkfr.load.loader import load_dataset
from dkfr.load.schema import apply_schema
from dkfr.load.validate import parse_named_queries, reconcile_counts, run_validation

VALIDATION_PATH = Path("cypher/validation.cypher")


def test_parse_named_queries_from_real_file():
    script = VALIDATION_PATH.read_text(encoding="utf-8")
    queries = parse_named_queries(script)
    names = [n for n, _ in queries]
    assert "match_has_exactly_two_sides" in names
    assert "played_in_goals_are_symmetric" in names
    assert len(queries) == 9
    for _name, query in queries:
        assert "RETURN" in query
        assert not query.strip().startswith("//")


def test_parse_named_queries_synthetic():
    script = """
    // NAME: check_one
    MATCH (n) WHERE n.bad RETURN n;

    // NAME: check_two
    MATCH (m) WHERE m.worse RETURN m;
    """
    queries = parse_named_queries(script)
    assert [n for n, _ in queries] == ["check_one", "check_two"]


@pytest.fixture
def live_driver():
    settings = get_settings()
    driver = build_driver(settings)
    try:
        driver.verify_connectivity()
    except Exception:
        pytest.skip("Neo4j not reachable — start it with `docker compose up -d`")
    yield driver, settings
    driver.close()


@pytest.mark.live_db
def test_validation_passes_and_reconciles_against_real_loaded_graph(live_driver):
    driver, settings = live_driver
    if not (settings.normalized_dir / "matches.jsonl").exists():
        pytest.skip("data/normalized not present — run `dkfr parse` first")

    run_write_query(driver, "MATCH (n) DETACH DELETE n")
    apply_schema(driver)
    load_dataset(driver, settings.normalized_dir)

    results = run_validation(driver)
    failed = [r for r in results if not r.passed]
    assert not failed, f"unexpected validation failures: {[r.name for r in failed]}"

    reconciliation = reconcile_counts(driver, settings.normalized_dir)
    mismatched = {k: v for k, v in reconciliation.items() if not v["match"]}
    assert not mismatched, f"reconciliation mismatches: {mismatched}"


@pytest.mark.live_db
def test_each_invariant_actually_fires_on_corruption(live_driver):
    """Proves the assertions aren't vacuously true — corrupt one real
    PLAYED_IN outcome and one real Match's puljeId scalar, confirm each
    corresponding check goes from PASS to FAIL, then restore via reload."""
    driver, settings = live_driver
    if not (settings.normalized_dir / "matches.jsonl").exists():
        pytest.skip("data/normalized not present — run `dkfr parse` first")

    run_write_query(driver, "MATCH (n) DETACH DELETE n")
    apply_schema(driver)
    load_dataset(driver, settings.normalized_dir)

    try:
        run_write_query(
            driver,
            """
            MATCH (t:Team)-[p:PLAYED_IN {side: 'HOME'}]->(m:Match)
            WHERE p.goalsFor > p.goalsAgainst
            WITH p LIMIT 1
            SET p.outcome = 'DRAW'
            """,
        )
        results = run_validation(driver)
        by_name = {r.name: r for r in results}
        assert not by_name["played_in_outcome_and_points_agree_with_goals"].passed

        run_write_query(driver, "MATCH (m:Match) WITH m LIMIT 1 SET m.puljeId = 999999")
        results = run_validation(driver)
        by_name = {r.name: r for r in results}
        assert not by_name["match_scalars_agree_with_stage"].passed
    finally:
        run_write_query(driver, "MATCH (n) DETACH DELETE n")
        load_dataset(driver, settings.normalized_dir)
