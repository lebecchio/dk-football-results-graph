"""Fetch every pulje declared in manifest/puljer.yaml: kampprogramFuld
(fixtures), stillingFuld (standings, for validation), and holdoversigt
(team roster, for team-identity resolution) — 3 requests per pulje (spec
R2.2), all through the polite, cached, logged T2 Fetcher.
"""

from __future__ import annotations

from rich.console import Console

from dkfr.config import Settings
from dkfr.fetch.build import build_fetcher
from dkfr.fetch.client import FetchError
from dkfr.manifest import load_manifest

VIEWS = ("kampprogramFuld", "stillingFuld", "holdoversigt")


def fetch_all_manifest_puljer(*, settings: Settings, console: Console) -> None:
    manifest = load_manifest(settings.puljer_manifest_path)
    total = len(manifest.puljer) * len(VIEWS)
    done = 0
    failed: list[str] = []

    with build_fetcher(settings, run_id="fetch-all") as fetcher:
        for pulje in manifest.puljer:
            for view in VIEWS:
                url = f"{settings.base_url}/resultater/pulje/{pulje.puljeId}/{view}"
                done += 1
                try:
                    result = fetcher.fetch(url, critical=True)
                except FetchError as exc:
                    failed.append(url)
                    console.print(f"[red]FAIL[/red] ({done}/{total}) {url}: {exc}")
                    continue
                tag = "cache" if result.from_cache else "net  "
                console.print(f"[{tag}] ({done}/{total}) {url}")

    if failed:
        console.print(f"\n[red]{len(failed)} fetch(es) failed:[/red]")
        for url in failed:
            console.print(f"  {url}")
        raise SystemExit(1)

    console.print(f"\n[green]Done[/green] — {total} requests across {len(manifest.puljer)} puljer.")
