"""AC7: parsing twice from a warm cache produces byte-identical normalized
output, with zero network access in between.

Runs against the real T3/T4/T6 cache (data/cache/, gitignored) — skips
cleanly if it isn't present (e.g. a fresh checkout with no prior fetch).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dkfr.manifest import load_manifest
from dkfr.normalize.build import build_dataset
from dkfr.normalize.resolver import TeamResolver, load_club_overrides
from dkfr.normalize.writer import write_normalized_dataset
from dkfr.parse.run import parse_all

MANIFEST_PATH = Path("manifest/puljer.yaml")
CLUBS_PATH = Path("manifest/clubs.yaml")
CACHE_DIR = Path("data/cache")


def _run_once(out_dir: Path) -> dict[str, str]:
    manifest = load_manifest(MANIFEST_PATH)
    results, _ = parse_all(manifest, CACHE_DIR)
    overrides = load_club_overrides(CLUBS_PATH)
    dataset = build_dataset(manifest, results, TeamResolver(club_overrides=overrides))
    paths = write_normalized_dataset(dataset, out_dir)
    return {name: path.read_text(encoding="utf-8") for name, path in paths.items()}


@pytest.mark.live_cache
def test_reparse_is_byte_identical(tmp_path):
    if not CACHE_DIR.exists():
        pytest.skip("data/cache not present — run `dkfr fetch --all` first")

    run1 = _run_once(tmp_path / "run1")
    run2 = _run_once(tmp_path / "run2")

    assert run1.keys() == run2.keys()
    for name in run1:
        assert run1[name] == run2[name], f"{name} differs between runs"


@pytest.mark.live_cache
def test_every_match_record_has_all_required_fields(tmp_path):
    """AC3: every match record carries the full required field set."""
    if not CACHE_DIR.exists():
        pytest.skip("data/cache not present — run `dkfr fetch --all` first")

    _run_once(tmp_path / "run")
    matches_path = tmp_path / "run" / "matches.jsonl"
    lines = matches_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) > 1000  # sanity: the real manifest has ~2000 matches

    required = {
        "date",
        "homeTeamId",
        "homeTeamName",
        "awayTeamId",
        "awayTeamName",
        "homeGoals",
        "awayGoals",
        "puljeId",
        "competitionId",
        "competitionName",
        "tier",
        "phase",
        "season",
        "gender",
        "ageBracket",
        "sourceUrl",
        "fetchedAt",
        "scraperVersion",
        "status",
    }
    for line in lines:
        record = json.loads(line)
        missing = required - set(record.keys())
        assert not missing, f"record missing fields: {missing}"
        assert record["fetchedAt"], "fetchedAt must not be empty (AC3 provenance)"
        assert record["sourceUrl"].startswith("https://www.dbu.dk/resultater/pulje/")
