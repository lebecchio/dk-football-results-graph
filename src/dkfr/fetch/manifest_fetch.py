"""Fetch every pulje declared in manifest/puljer.yaml (fixtures + standings + teams).

Implemented in T4/T6 once the manifest module exists. Placeholder for T2.
"""

from __future__ import annotations

from rich.console import Console

from dkfr.config import Settings


def fetch_all_manifest_puljer(*, settings: Settings, console: Console) -> None:
    raise NotImplementedError(
        "Manifest-driven fetch is implemented in T4/T6, once manifest/puljer.yaml "
        "and dkfr.manifest exist. Use `dkfr fetch --url <url>` for one-off fetches."
    )
