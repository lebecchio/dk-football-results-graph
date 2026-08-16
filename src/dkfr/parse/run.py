"""Run the full parse pass across every manifest pulje's cached HTML.

Zero network access (spec R2.6/design boundary [1]->[2]) — reads only
data/cache/. Produces the parsed record sets plus a combined ParseIssue
list; data/reports/parse-issues.json is written by the caller (parse_cmd).

Each view's real dbu.dk source URL and fetch timestamp are read back from
the cache's own .meta.json sidecar (dkfr.fetch.cache.CacheMeta) — never
reconstructed or stamped from wall-clock time. That's what makes AC7
(byte-identical re-parse of a warm cache) achievable: fetchedAt is a fact
about when the *fetch* happened, sourced once, and is stable across any
number of re-parses.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from dkfr.manifest import Manifest, PuljeEntry
from dkfr.parse.fixtures import RawMatchRow, parse_fixtures
from dkfr.parse.issues import ParseIssue
from dkfr.parse.standings import StandingRow, parse_standings
from dkfr.parse.teams import TeamRosterEntry, parse_teams
from dkfr.vocab import ParseIssueSeverity

VIEWS = ("kampprogramFuld", "stillingFuld", "holdoversigt")


class ViewMeta(BaseModel):
    sourceUrl: str
    fetchedAt: str | None


class PuljeParseResult(BaseModel):
    pulje: PuljeEntry
    matches: list[RawMatchRow]
    standings: list[StandingRow]
    teams: list[TeamRosterEntry]
    issues: list[ParseIssue]
    fixturesMeta: ViewMeta
    standingsMeta: ViewMeta
    teamsMeta: ViewMeta


ERROR_ISSUE_THRESHOLD = 5  # AC11: fail loudly if error-severity issues exceed this


def _read_meta(html_path: Path, base_url: str, pulje_id: int, view: str) -> ViewMeta:
    default_url = f"{base_url}/resultater/pulje/{pulje_id}/{view}"
    meta_path = html_path.with_suffix(".meta.json")
    if meta_path.exists():
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return ViewMeta(sourceUrl=data.get("url", default_url), fetchedAt=data.get("fetchedAt"))
    return ViewMeta(sourceUrl=default_url, fetchedAt=None)


def parse_all(
    manifest: Manifest, cache_dir: Path, base_url: str = "https://www.dbu.dk"
) -> tuple[list[PuljeParseResult], list[ParseIssue]]:
    results: list[PuljeParseResult] = []
    all_issues: list[ParseIssue] = []

    for pulje in manifest.puljer:
        base = cache_dir / "pulje" / str(pulje.puljeId)
        kf = base / "kampprogramFuld.html"
        sf = base / "stillingFuld.html"
        hf = base / "holdoversigt.html"

        fixtures_meta = _read_meta(kf, base_url, pulje.puljeId, "kampprogramFuld")
        standings_meta = _read_meta(sf, base_url, pulje.puljeId, "stillingFuld")
        teams_meta = _read_meta(hf, base_url, pulje.puljeId, "holdoversigt")

        pulje_issues: list[ParseIssue] = []

        matches: list[RawMatchRow] = []
        if kf.exists():
            matches, issues = parse_fixtures(
                kf.read_text(encoding="utf-8"), fixtures_meta.sourceUrl
            )
            pulje_issues.extend(issues)
        else:
            pulje_issues.append(
                ParseIssue(
                    sourceUrl=fixtures_meta.sourceUrl,
                    rowIndex=-1,
                    rawRow="<missing file>",
                    reason=f"kampprogramFuld not found in cache for pulje {pulje.puljeId} "
                    "— run `dkfr fetch --all` first",
                    severity=ParseIssueSeverity.ERROR,
                )
            )

        standings: list[StandingRow] = []
        if sf.exists():
            standings, issues = parse_standings(
                sf.read_text(encoding="utf-8"), standings_meta.sourceUrl
            )
            pulje_issues.extend(issues)

        teams: list[TeamRosterEntry] = []
        if hf.exists():
            teams, issues = parse_teams(hf.read_text(encoding="utf-8"), teams_meta.sourceUrl)
            pulje_issues.extend(issues)

        results.append(
            PuljeParseResult(
                pulje=pulje,
                matches=matches,
                standings=standings,
                teams=teams,
                issues=pulje_issues,
                fixturesMeta=fixtures_meta,
                standingsMeta=standings_meta,
                teamsMeta=teams_meta,
            )
        )
        all_issues.extend(pulje_issues)

    return results, all_issues
