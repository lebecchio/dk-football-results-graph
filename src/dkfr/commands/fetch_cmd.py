"""`dkfr fetch` — stage 1. One-off URL fetch (--url) or full manifest fetch (--all)."""

from __future__ import annotations

from rich.console import Console

from dkfr.config import get_settings
from dkfr.fetch.build import build_fetcher


def run_fetch(*, url: str | None, all_manifest: bool, console: Console) -> None:
    settings = get_settings()

    if not url and not all_manifest:
        console.print("[yellow]Nothing to do — pass --url <url> or --all.[/yellow]")
        raise SystemExit(1)

    if url:
        with build_fetcher(settings) as fetcher:
            result = fetcher.fetch(url)
            console.print(
                f"[green]Fetched[/green] {url} "
                f"({'cache' if result.from_cache else 'network'}, "
                f"{len(result.html)} bytes, status={result.meta.status})"
            )
        return

    if all_manifest:
        from dkfr.fetch.manifest_fetch import fetch_all_manifest_puljer

        fetch_all_manifest_puljer(settings=settings, console=console)
