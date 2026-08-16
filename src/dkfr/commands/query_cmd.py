"""`dkfr query <name> --param key=value` — run a checked-in Cypher query."""

from __future__ import annotations

from rich.console import Console

from dkfr.config import get_settings
from dkfr.load.driver import build_driver
from dkfr.queries.runner import parse_params, print_results, run_query_file


def run_query(*, name: str, params: list[str], console: Console) -> None:
    settings = get_settings()
    driver = build_driver(settings)
    try:
        driver.verify_connectivity()
        parsed = parse_params(params)
        rows = run_query_file(driver, name, parsed)
        print_results(console, name, rows)
    finally:
        driver.close()
