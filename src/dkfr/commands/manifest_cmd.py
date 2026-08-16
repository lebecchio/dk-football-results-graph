"""`dkfr manifest verify` — AC1: every manifest pulje resolves to a live page
whose title matches the declared competition/phase/group/season."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from dkfr.config import get_settings
from dkfr.fetch.build import build_fetcher
from dkfr.manifest import VerifyResult, _title_from_html, check_pulje_title, load_manifest


def run_manifest_verify(*, console: Console) -> None:
    settings = get_settings()
    manifest = load_manifest(settings.puljer_manifest_path)

    table = Table(title="Manifest verification (AC1)")
    table.add_column("puljeId")
    table.add_column("competitionId")
    table.add_column("status")
    table.add_column("title / reason")

    results: list[VerifyResult] = []

    with build_fetcher(settings, run_id="manifest-verify") as fetcher:
        for pulje in manifest.puljer:
            competition = manifest.competition_for(pulje)
            url = f"{settings.base_url}/resultater/pulje/{pulje.puljeId}/stillingFuld"
            try:
                result = fetcher.fetch(url, critical=True)
            except Exception as exc:  # noqa: BLE001 — surfaced as a failed row, not a crash
                results.append(
                    VerifyResult(
                        puljeId=pulje.puljeId,
                        competitionId=pulje.competitionId,
                        ok=False,
                        fetchFailed=True,
                        reason=str(exc),
                        url=url,
                    )
                )
                continue

            title = _title_from_html(result.html)
            reason = check_pulje_title(title, competition, pulje)
            results.append(
                VerifyResult(
                    puljeId=pulje.puljeId,
                    competitionId=pulje.competitionId,
                    ok=reason is None,
                    fetchedTitle=title,
                    reason=reason,
                    url=url,
                )
            )

    for r in results:
        if r.ok:
            table.add_row(
                str(r.puljeId), r.competitionId, "[green]OK[/green]", r.fetchedTitle or ""
            )
        else:
            status = "[red]FETCH FAIL[/red]" if r.fetchFailed else "[red]MISMATCH[/red]"
            table.add_row(str(r.puljeId), r.competitionId, status, r.reason or "")

    ok_count = sum(1 for r in results if r.ok)
    fail_count = len(results) - ok_count

    console.print(table)
    console.print(f"\n{ok_count} OK, {fail_count} failed, {len(manifest.puljer)} total entries.")
    if fail_count:
        raise SystemExit(1)
