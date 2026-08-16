"""Run the full parse pass across every manifest pulje's cached HTML.

Zero network access (spec R2.6/design boundary [1]->[2]) — reads only
data/cache/. Produces the parsed record sets plus a combined ParseIssue
list; data/reports/parse-issues.json is written by the caller (parse_cmd).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from dkfr.manifest import Manifest, PuljeEntry
from dkfr.parse.fixtures import RawMatchRow, parse_fixtures
from dkfr.parse.issues import ParseIssue
from dkfr.parse.standings import StandingRow, parse_standings
from dkfr.parse.teams import TeamRosterEntry, parse_teams


class PuljeParseResult(BaseModel):
    pulje: PuljeEntry
    matches: list[RawMatchRow]
    standings: list[StandingRow]
    teams: list[TeamRosterEntry]
    issues: list[ParseIssue]


ERROR_ISSUE_THRESHOLD = 5  # AC11: fail loudly if error-severity issues exceed this


def parse_all(
    manifest: Manifest, cache_dir: Path
) -> tuple[list[PuljeParseResult], list[ParseIssue]]:
    results: list[PuljeParseResult] = []
    all_issues: list[ParseIssue] = []

    for pulje in manifest.puljer:
        base = cache_dir / "pulje" / str(pulje.puljeId)
        kf = base / "kampprogramFuld.html"
        sf = base / "stillingFuld.html"
        hf = base / "holdoversigt.html"

        pulje_issues: list[ParseIssue] = []

        matches: list[RawMatchRow] = []
        if kf.exists():
            matches, issues = parse_fixtures(kf.read_text(encoding="utf-8"), str(kf))
            pulje_issues.extend(issues)
        else:
            pulje_issues.append(
                ParseIssue(
                    sourceUrl=str(kf),
                    rowIndex=-1,
                    rawRow="<missing file>",
                    reason=f"kampprogramFuld not found in cache for pulje {pulje.puljeId} "
                    "— run `dkfr fetch --all` first",
                    severity="ERROR",
                )
            )

        standings: list[StandingRow] = []
        if sf.exists():
            standings, issues = parse_standings(sf.read_text(encoding="utf-8"), str(sf))
            pulje_issues.extend(issues)

        teams: list[TeamRosterEntry] = []
        if hf.exists():
            teams, issues = parse_teams(hf.read_text(encoding="utf-8"), str(hf))
            pulje_issues.extend(issues)

        results.append(
            PuljeParseResult(
                pulje=pulje,
                matches=matches,
                standings=standings,
                teams=teams,
                issues=pulje_issues,
            )
        )
        all_issues.extend(pulje_issues)

    return results, all_issues
