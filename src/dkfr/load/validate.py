"""Runs cypher/validation.cypher's named assertions + JSON<->graph count
reconciliation + standings reconciliation. AC13/14/15/8.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel

from dkfr.load.driver import run_read

VALIDATION_PATH = Path(__file__).resolve().parents[3] / "cypher" / "validation.cypher"

_NAME_MARKER_RE = re.compile(r"//\s*NAME:\s*(\S+)")


class ValidationResult(BaseModel):
    name: str
    query: str
    violations: list[dict]
    passed: bool


def parse_named_queries(script: str) -> list[tuple[str, str]]:
    """Split validation.cypher into (name, query) pairs using the `// NAME:`
    marker convention documented in the file's own header comment."""
    blocks = re.split(r"(?=// NAME:)", script)
    queries: list[tuple[str, str]] = []
    for block in blocks:
        m = _NAME_MARKER_RE.search(block)
        if not m:
            continue
        name = m.group(1)
        # Drop every comment line, keep the rest, strip the trailing ';'.
        lines = [
            line
            for line in block.splitlines()
            if line.strip() and not line.strip().startswith("//")
        ]
        query = "\n".join(lines).strip().rstrip(";").strip()
        if query:
            queries.append((name, query))
    return queries


def run_validation(driver, validation_path: Path = VALIDATION_PATH) -> list[ValidationResult]:
    script = validation_path.read_text(encoding="utf-8")
    results = []
    for name, query in parse_named_queries(script):
        violations = run_read(driver, query)
        results.append(
            ValidationResult(
                name=name, query=query, violations=violations, passed=len(violations) == 0
            )
        )
    return results


def reconcile_counts(driver, normalized_dir: Path) -> dict[str, dict[str, int]]:
    """AC15: node/relationship counts in the graph vs. record counts in the
    normalized JSON."""

    def _jsonl_count(path: Path) -> int:
        if not path.exists():
            return 0
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())

    def _json_count(path: Path) -> int:
        if not path.exists():
            return 0
        return len(json.loads(path.read_text(encoding="utf-8")))

    json_counts = {
        "Match": _jsonl_count(normalized_dir / "matches.jsonl"),
        "PARTICIPATED_IN": _jsonl_count(normalized_dir / "standings.jsonl"),
        "Team": _json_count(normalized_dir / "teams.json"),
        "Club": _json_count(normalized_dir / "clubs.json"),
        "Venue": _json_count(normalized_dir / "venues.json"),
        "Competition": _json_count(normalized_dir / "competitions.json"),
        "Stage": _json_count(normalized_dir / "puljer.json"),
    }

    node_rows = run_read(driver, "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS cnt")
    rel_rows = run_read(driver, "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS cnt")
    graph_counts = {row["label"]: row["cnt"] for row in node_rows}
    graph_counts.update({row["type"]: row["cnt"] for row in rel_rows})

    reconciliation = {}
    for key, expected in json_counts.items():
        actual = graph_counts.get(key, 0)
        reconciliation[key] = {"expected": expected, "actual": actual, "match": expected == actual}
    return reconciliation
