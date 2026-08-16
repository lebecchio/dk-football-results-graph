"""`dkfr parse` — stage 2: HTML cache -> normalized JSON. Zero network access."""

from __future__ import annotations

import json

from rich.console import Console

from dkfr.config import get_settings
from dkfr.manifest import load_manifest
from dkfr.normalize.build import build_dataset
from dkfr.normalize.resolver import TeamResolver, load_club_overrides
from dkfr.normalize.writer import write_normalized_dataset
from dkfr.parse.run import ERROR_ISSUE_THRESHOLD, parse_all
from dkfr.vocab import ParseIssueSeverity


def run_parse(*, console: Console) -> None:
    settings = get_settings()
    manifest = load_manifest(settings.puljer_manifest_path)

    results, issues = parse_all(manifest, settings.cache_dir, base_url=settings.base_url)

    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    issues_path = settings.reports_dir / "parse-issues.json"
    issues_path.write_text(
        json.dumps([i.model_dump() for i in issues], indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    error_count = sum(1 for i in issues if i.severity == ParseIssueSeverity.ERROR)
    console.print(f"Parsed {len(results)} puljer, {len(issues)} issue(s) ({error_count} errors).")
    console.print(f"Issue report: {issues_path}")

    club_overrides = load_club_overrides(settings.clubs_path)
    resolver = TeamResolver(club_overrides=club_overrides)
    dataset = build_dataset(manifest, results, resolver)

    paths = write_normalized_dataset(dataset, settings.normalized_dir)
    for name, path in paths.items():
        console.print(f"Wrote {name}: {path}")

    console.print(
        f"\n{len(dataset.matches)} matches, {len(dataset.teams)} teams, "
        f"{len(dataset.clubs)} clubs, {len(dataset.venues)} venues, "
        f"{len(dataset.standings)} standing rows."
    )

    if error_count > ERROR_ISSUE_THRESHOLD:
        console.print(
            f"[red]{error_count} error-severity parse issues exceeds threshold "
            f"({ERROR_ISSUE_THRESHOLD}) — failing loudly per AC11.[/red]"
        )
        raise SystemExit(1)
