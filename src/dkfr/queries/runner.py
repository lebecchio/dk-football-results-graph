"""Loads a .cypher file from queries/, binds --param values, prints a table.
Makes AC16's "checked-in queries" executable and testable."""

from __future__ import annotations

import re
from pathlib import Path

from rich.console import Console
from rich.table import Table

from dkfr.load.driver import run_read

QUERIES_DIR = Path(__file__).resolve().parents[3] / "queries"

_INT_RE = re.compile(r"^-?\d+$")


def load_query(name: str, queries_dir: Path = QUERIES_DIR) -> str:
    path = queries_dir / f"{name}.cypher"
    if not path.exists():
        raise FileNotFoundError(f"No such query file: {path}")
    text = path.read_text(encoding="utf-8")
    # Strip leading `//` comment lines (the header block) but keep the query.
    lines = [line for line in text.splitlines() if not line.strip().startswith("//")]
    return "\n".join(lines).strip().rstrip(";").strip()


def parse_params(raw_params: list[str]) -> dict[str, object]:
    """Parse `key=value` strings, coercing plain integers to int."""
    params: dict[str, object] = {}
    for raw in raw_params:
        if "=" not in raw:
            raise ValueError(f"--param must be key=value, got {raw!r}")
        key, value = raw.split("=", 1)
        params[key] = int(value) if _INT_RE.match(value) else value
    return params


def run_query_file(driver, name: str, params: dict[str, object]) -> list[dict]:
    query = load_query(name)
    return run_read(driver, query, **params)


def print_results(console: Console, name: str, rows: list[dict]) -> None:
    if not rows:
        console.print(f"[yellow]{name}: 0 rows[/yellow]")
        return
    table = Table(title=name)
    for col in rows[0]:
        table.add_column(str(col))
    for row in rows:
        table.add_row(*(str(v) for v in row.values()))
    console.print(table)
