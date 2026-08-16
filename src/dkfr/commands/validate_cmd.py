"""`dkfr validate` — stage 4: post-load invariant checks + reconciliation."""

from __future__ import annotations

import json

from rich.console import Console
from rich.table import Table

from dkfr.config import get_settings
from dkfr.load.driver import build_driver
from dkfr.load.validate import reconcile_counts, run_validation


def run_validate(*, console: Console) -> None:
    settings = get_settings()
    driver = build_driver(settings)
    try:
        driver.verify_connectivity()

        results = run_validation(driver)
        table = Table(title="Post-load validation (AC13)")
        table.add_column("check")
        table.add_column("status")
        table.add_column("violations")
        any_failed = False
        for r in results:
            if r.passed:
                table.add_row(r.name, "[green]PASS[/green]", "0")
            else:
                any_failed = True
                table.add_row(r.name, "[red]FAIL[/red]", str(len(r.violations)))
        console.print(table)

        reconciliation = reconcile_counts(driver, settings.normalized_dir)
        recon_table = Table(title="Graph <-> JSON reconciliation (AC15)")
        recon_table.add_column("entity")
        recon_table.add_column("expected (JSON)")
        recon_table.add_column("actual (graph)")
        recon_table.add_column("status")
        recon_failed = False
        for key, row in reconciliation.items():
            status = "[green]OK[/green]" if row["match"] else "[red]MISMATCH[/red]"
            if not row["match"]:
                recon_failed = True
            recon_table.add_row(key, str(row["expected"]), str(row["actual"]), status)
        console.print(recon_table)

        settings.reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = settings.reports_dir / "validation.json"
        report_path.write_text(
            json.dumps(
                {
                    "invariants": [r.model_dump() for r in results],
                    "reconciliation": reconciliation,
                },
                indent=2,
                sort_keys=True,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )
        console.print(f"Wrote {report_path}")

        if any_failed or recon_failed:
            raise SystemExit(1)
    finally:
        driver.close()
