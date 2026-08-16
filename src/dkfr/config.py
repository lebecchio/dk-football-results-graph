"""Pipeline configuration, loaded from environment / .env via pydantic-settings.

DBU_CONTACT_EMAIL has NO default. The honest, descriptive User-Agent requirement
(spec R2.4) is structural: the tool refuses to construct a Fetcher without a
contact address to put in it, rather than falling back to a generic UA.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Identity / politeness ---
    dbu_contact_email: str = Field(
        ...,
        description=(
            "Contact email embedded in the User-Agent sent to dbu.dk. Required, "
            "no default — see spec R2.4. Set DBU_CONTACT_EMAIL in .env."
        ),
    )
    project_name: str = "dk-football-results-graph"
    project_url: str = "https://github.com/example/dk-football-results-graph"

    # --- Fetch behaviour ---
    min_request_interval_seconds: float = 2.0
    request_timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_base_delay_seconds: float = 5.0

    # --- Paths (all data/ is gitignored — R3.7 / AC21) ---
    data_dir: Path = REPO_ROOT / "data"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def normalized_dir(self) -> Path:
        return self.data_dir / "normalized"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    # --- Manifest / curated data ---
    manifest_dir: Path = REPO_ROOT / "manifest"

    @property
    def puljer_manifest_path(self) -> Path:
        return self.manifest_dir / "puljer.yaml"

    @property
    def aliases_path(self) -> Path:
        return self.manifest_dir / "aliases.yaml"

    @property
    def clubs_path(self) -> Path:
        return self.manifest_dir / "clubs.yaml"

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme12345"

    # --- Source ---
    base_url: str = "https://www.dbu.dk"
    # Everything under /resultater/ is fetchable EXCEPT the two robots-disallowed
    # subpaths (checked separately, defense-in-depth, by RobotsChecker — see
    # fetch/robots.py). Spec F5 confirms pulje/kamp/klub/raekke/hold are all
    # not disallowed; the bare /resultater/ landing page isn't in the Disallow
    # list either. This is deliberately broad rather than pulje-only, because T3
    # (discovery) also needs the /resultater/raekke/ page and the landing page —
    # no image/asset paths live under /resultater/ in the first place, so this
    # does not weaken R2.8 (no logos/assets, ever).
    allowed_path_prefixes: tuple[str, ...] = ("/resultater/",)
    disallowed_path_prefixes: tuple[str, ...] = (
        "/resultater/kampsoegAdvanceret/",
        "/turneringer_og_resultater/resultatsoegning/",
    )

    def user_agent(self) -> str:
        return (
            f"{self.project_name}/1.0 (personal research project, non-commercial; "
            f"+{self.project_url}; contact: {self.dbu_contact_email})"
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
