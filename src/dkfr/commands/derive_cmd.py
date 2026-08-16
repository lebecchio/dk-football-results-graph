"""`dkfr derive` — rebuild the derived PLAYED_AGAINST projection."""

from __future__ import annotations

from rich.console import Console

from dkfr.config import get_settings
from dkfr.load.derive import run_derive
from dkfr.load.driver import build_driver, run_read


def run_derive_cmd(*, console: Console) -> None:
    settings = get_settings()
    driver = build_driver(settings)
    try:
        driver.verify_connectivity()
        run_derive(driver)
        count = run_read(driver, "MATCH ()-[r:PLAYED_AGAINST]->() RETURN count(*) AS cnt")[0]["cnt"]
        console.print(f"[green]Rebuilt PLAYED_AGAINST[/green] — {count} relationships.")
    finally:
        driver.close()
