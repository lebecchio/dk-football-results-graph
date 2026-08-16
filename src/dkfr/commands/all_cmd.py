"""`dkfr all` — run the full pipeline: fetch -> parse -> load -> derive ->
validate, in order."""

from __future__ import annotations

from rich.console import Console

from dkfr.config import get_settings


def run_all(*, console: Console) -> None:
    settings = get_settings()

    console.rule("[bold]1/5 fetch[/bold]")
    from dkfr.fetch.manifest_fetch import fetch_all_manifest_puljer

    fetch_all_manifest_puljer(settings=settings, console=console)

    console.rule("[bold]2/5 parse[/bold]")
    from dkfr.commands.parse_cmd import run_parse

    run_parse(console=console)

    console.rule("[bold]3/5 load[/bold]")
    from dkfr.commands.load_cmd import run_load

    run_load(schema_only=False, console=console)

    console.rule("[bold]4/5 derive[/bold]")
    from dkfr.commands.derive_cmd import run_derive_cmd

    run_derive_cmd(console=console)

    console.rule("[bold]5/5 validate[/bold]")
    from dkfr.commands.validate_cmd import run_validate

    run_validate(console=console)

    console.rule("[bold green]done[/bold green]")
