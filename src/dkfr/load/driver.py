"""Neo4j driver/session lifecycle and a batching helper for UNWIND-based
writes (design: "batched UNWIND + MERGE, 500/batch, execute_write")."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from neo4j import GraphDatabase, ManagedTransaction

from dkfr.config import Settings

DEFAULT_BATCH_SIZE = 500


def build_driver(settings: Settings):
    return GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )


def batched(rows: list[dict], size: int = DEFAULT_BATCH_SIZE) -> Iterator[list[dict]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def run_unwind_write(
    driver, cypher: str, rows: list[dict[str, Any]], batch_size: int = DEFAULT_BATCH_SIZE
) -> int:
    """Run `cypher` (which must reference `$rows` via an UNWIND) once per
    batch, inside a single write transaction per batch. Returns the total
    row count written."""
    total = 0
    with driver.session() as session:
        for batch in batched(rows, batch_size):
            session.execute_write(_run_batch, cypher, batch)
            total += len(batch)
    return total


def _run_batch(tx: ManagedTransaction, cypher: str, rows: list[dict]) -> None:
    tx.run(cypher, rows=rows)


def run_read(driver, cypher: str, **params) -> list[dict]:
    with driver.session() as session:
        result = session.run(cypher, **params)
        return [dict(record) for record in result]


def run_write_query(driver, cypher: str, **params) -> list[dict]:
    with driver.session() as session:
        result = session.execute_write(lambda tx: list(tx.run(cypher, **params)))
        return [dict(record) for record in result]


def iter_statements(script: str) -> Iterable[str]:
    """Split a .cypher file into individual statements on top-level `;`,
    skipping blank/comment-only lines. Good enough for our schema/derive/
    validation files, which don't embed semicolons in string literals."""
    for raw_stmt in script.split(";"):
        lines = [
            line
            for line in raw_stmt.splitlines()
            if line.strip() and not line.strip().startswith("//")
        ]
        stmt = "\n".join(lines).strip()
        if stmt:
            yield stmt
