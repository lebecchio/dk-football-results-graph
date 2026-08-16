"""dkfr — one CLI, one subcommand per pipeline stage (spec AC20).

Stages: fetch -> parse -> load -> derive -> validate, plus query/manifest/names
utilities and an `all` convenience command that runs the whole pipeline.
"""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(
    name="dkfr",
    help="Danish football (DBU) results scraper -> Neo4j graph, 2025/26 season.",
    no_args_is_help=True,
)
manifest_app = typer.Typer(help="Manifest curation and verification.")
names_app = typer.Typer(help="Team-name resolution review.")
app.add_typer(manifest_app, name="manifest")
app.add_typer(names_app, name="names")

console = Console()


@app.command()
def fetch(
    url: str = typer.Option(
        None, "--url", help="Fetch a single URL for one-off inspection (bypasses the manifest)."
    ),
    all_manifest: bool = typer.Option(
        False, "--all", help="Fetch every pulje in manifest/puljer.yaml (fixtures/standings/teams)."
    ),
) -> None:
    """Stage 1: fetch and cache raw HTML from dbu.dk. Zero parsing happens here."""
    from dkfr.commands.fetch_cmd import run_fetch

    run_fetch(url=url, all_manifest=all_manifest, console=console)


@app.command()
def parse() -> None:
    """Stage 2: parse the HTML cache into normalized JSON. Zero network access."""
    from dkfr.commands.parse_cmd import run_parse

    run_parse(console=console)


@app.command()
def load(
    schema_only: bool = typer.Option(
        False, "--schema-only", help="Only apply cypher/schema.cypher, skip data load."
    ),
) -> None:
    """Stage 3: load normalized JSON into Neo4j (idempotent MERGE)."""
    from dkfr.commands.load_cmd import run_load

    run_load(schema_only=schema_only, console=console)


@app.command()
def derive() -> None:
    """Rebuild the derived PLAYED_AGAINST projection (drop-and-rebuild, idempotent)."""
    from dkfr.commands.derive_cmd import run_derive_cmd

    run_derive_cmd(console=console)


@app.command()
def validate() -> None:
    """Stage 4: run post-load invariant checks and reconciliation reports."""
    from dkfr.commands.validate_cmd import run_validate

    run_validate(console=console)


@app.command()
def query(
    name: str = typer.Argument(
        ..., help="Query file name under queries/, e.g. u01-opponents."
    ),
    param: list[str] = typer.Option(
        [], "--param", help="key=value query parameter, repeatable."
    ),
) -> None:
    """Run a checked-in Cypher query from queries/ against the loaded graph."""
    from dkfr.commands.query_cmd import run_query

    run_query(name=name, params=param, console=console)


@app.command(name="all")
def run_all() -> None:
    """Run the full pipeline: fetch -> parse -> load -> derive -> validate."""
    from dkfr.commands.all_cmd import run_all as _run_all

    _run_all(console=console)


@manifest_app.command("verify")
def manifest_verify() -> None:
    """Fetch each manifest pulje's landing page and confirm its title matches (AC1)."""
    from dkfr.commands.manifest_cmd import run_manifest_verify

    run_manifest_verify(console=console)


@names_app.command("review")
def names_review() -> None:
    """Print/regenerate the unresolved team-name report with rapidfuzz suggestions."""
    from dkfr.commands.names_cmd import run_names_review

    run_names_review(console=console)


if __name__ == "__main__":
    app()
