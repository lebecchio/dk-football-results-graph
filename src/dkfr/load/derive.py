"""Rebuilds the derived PLAYED_AGAINST projection (cypher/derive.cypher).
Full drop-and-rebuild — idempotent by construction (design OQ-1)."""

from __future__ import annotations

from pathlib import Path

from dkfr.load.driver import run_write_query
from dkfr.load.validate import parse_named_queries

DERIVE_PATH = Path(__file__).resolve().parents[3] / "cypher" / "derive.cypher"


def run_derive(driver, derive_path: Path = DERIVE_PATH) -> dict[str, int]:
    script = derive_path.read_text(encoding="utf-8")
    stats: dict[str, int] = {}
    for name, query in parse_named_queries(script):
        run_write_query(driver, query)
        stats[name] = 1
    return stats
