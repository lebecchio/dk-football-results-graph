"""`dkfr load` — stage 3: apply schema, then load normalized JSON into Neo4j."""

from __future__ import annotations

from rich.console import Console

from dkfr.config import get_settings
from dkfr.load.driver import build_driver
from dkfr.load.schema import apply_schema


def run_load(*, schema_only: bool, console: Console) -> None:
    settings = get_settings()
    driver = build_driver(settings)
    try:
        driver.verify_connectivity()
        n = apply_schema(driver)
        console.print(f"[green]Applied {n} schema statement(s).[/green]")

        if schema_only:
            return

        from dkfr.load.loader import load_dataset

        stats = load_dataset(driver, settings.normalized_dir)
        for label, count in stats.items():
            console.print(f"  {label}: {count}")
    finally:
        driver.close()
