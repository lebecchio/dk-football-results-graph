"""Applies cypher/schema.cypher. AC12."""

from __future__ import annotations

from pathlib import Path

from dkfr.load.driver import iter_statements

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "cypher" / "schema.cypher"


def apply_schema(driver, schema_path: Path = SCHEMA_PATH) -> int:
    script = schema_path.read_text(encoding="utf-8")
    count = 0
    with driver.session() as session:
        for stmt in iter_statements(script):
            session.run(stmt)
            count += 1
    return count
