"""`dkfr names review` — regenerate data/reports/unresolved-names.json."""

from __future__ import annotations

from rich.console import Console

from dkfr.config import get_settings
from dkfr.normalize.review import write_review_report


def run_names_review(*, console: Console) -> None:
    settings = get_settings()
    out_path = settings.reports_dir / "unresolved-names.json"
    report = write_review_report(
        manifest_path=settings.puljer_manifest_path,
        clubs_path=settings.clubs_path,
        cache_dir=settings.cache_dir,
        out_path=out_path,
    )
    console.print(f"Wrote {out_path}")
    console.print(f"Unresolved names: {report['summary']['totalUnresolvedNames']}")
    console.print(f"Club-grouping suspects: {report['summary']['totalClubGroupingSuspects']}")
