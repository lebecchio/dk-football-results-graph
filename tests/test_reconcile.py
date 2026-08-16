"""dkfr.load.reconcile — AC8 standings reconciliation tests (marked live_db)."""

from __future__ import annotations

import pytest

from dkfr.config import get_settings
from dkfr.load.driver import build_driver
from dkfr.load.reconcile import reconcile_all
from dkfr.manifest import load_manifest


@pytest.mark.live_db
def test_at_least_five_non_carry_over_puljer_reconcile_exactly():
    """AC8: at least 5 puljer spanning different tiers and brackets reconcile
    exactly on played/won/drawn/lost/GF/GA/points."""
    settings = get_settings()
    if not (settings.normalized_dir / "matches.jsonl").exists():
        pytest.skip("data/normalized not present — run `dkfr parse` first")

    driver = build_driver(settings)
    try:
        driver.verify_connectivity()
    except Exception:
        pytest.skip("Neo4j not reachable — start it with `docker compose up -d`")

    try:
        manifest = load_manifest(settings.puljer_manifest_path)
        results = reconcile_all(driver, manifest)
        compared = [r for r in results if r.compared]
        clean = [r for r in compared if r.passed]

        assert len(clean) >= 5, f"only {len(clean)} puljer reconciled exactly: {results}"

        # Confirm they span different tiers/brackets, not 5 copies of the
        # same competition.
        clean_puljer_ids = {r.puljeId for r in clean}
        competitions_involved = {
            p.competitionId for p in manifest.puljer if p.puljeId in clean_puljer_ids
        }
        assert len(competitions_involved) >= 2, "clean puljer should span multiple competitions"
    finally:
        driver.close()


@pytest.mark.live_db
def test_carry_over_puljer_are_reported_separately_not_as_failures():
    """R-3 / T14: a pointsCarryOver pulje must never appear as a failed
    comparison — it's explicitly skipped with a note, not force-compared."""
    settings = get_settings()
    if not (settings.normalized_dir / "matches.jsonl").exists():
        pytest.skip("data/normalized not present — run `dkfr parse` first")

    driver = build_driver(settings)
    try:
        driver.verify_connectivity()
    except Exception:
        pytest.skip("Neo4j not reachable — start it with `docker compose up -d`")

    try:
        manifest = load_manifest(settings.puljer_manifest_path)
        results = reconcile_all(driver, manifest)
        carry_over_results = [r for r in results if r.pointsCarryOver]
        assert carry_over_results, "expected at least one carry-over pulje in the manifest"
        for r in carry_over_results:
            assert r.compared is False
            assert r.passed is True
            assert r.note is not None
    finally:
        driver.close()
