"""Parse a `holdoversigt` page into (dbuTeamId, displayName, stadiumName).

Confirmed structure (docs/specs/dk-results-scraper/discovery-notes.md): NOT
a <table> — a `<div class="sr--pool--team-list--team">` per team, with
`onclick="window.location.href = '/resultater/hold/<id>_<puljeId>/'"`
row-navigation (same pattern as the multi-pulje Raekke pages).

PRIVACY (spec C6/N4): this page also renders a named head coach per team
(`.sr--pool--team-list--team--coach`). This parser MUST NOT extract, store,
or pass through that field — confirmed real named individuals appear there
during the T3 spike (e.g. a real coach name for a Herre-DS team). Only
(dbuTeamId, displayName, stadiumName) are extracted, by construction: the
coach subtree is never even queried.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from dkfr.parse.issues import ParseIssue
from dkfr.parse.tables import parse_html, row_link
from dkfr.vocab import ParseIssueSeverity

TEAM_ID_RE_FROM_ONCLICK = re.compile(r"/resultater/hold/(\d+)_(\d+)")


class TeamRosterEntry(BaseModel):
    dbuTeamId: str | None
    displayName: str
    stadiumName: str | None


def parse_teams(html: str, source_url: str) -> tuple[list[TeamRosterEntry], list[ParseIssue]]:
    soup = parse_html(html)
    team_divs = soup.find_all("div", class_="sr--pool--team-list--team")

    if not team_divs:
        return [], [
            ParseIssue(
                sourceUrl=source_url,
                rowIndex=-1,
                rawRow="<no team entries found>",
                reason="holdoversigt page has no sr--pool--team-list--team divs",
                severity=ParseIssueSeverity.ERROR,
            )
        ]

    entries: list[TeamRosterEntry] = []
    issues: list[ParseIssue] = []

    for row_index, team_div in enumerate(team_divs, start=1):
        name_div = team_div.find("div", class_="sr--pool--team-list--team--name")
        name_text = name_div.get_text(strip=True) if name_div else ""

        if not name_text:
            issues.append(
                ParseIssue(
                    sourceUrl=source_url,
                    rowIndex=row_index,
                    rawRow=str(team_div)[:200],
                    reason="team entry has no name text",
                    severity=ParseIssueSeverity.ERROR,
                )
            )
            continue

        href = row_link(team_div)
        m = TEAM_ID_RE_FROM_ONCLICK.search(href) if href else None
        dbu_team_id = m.group(1) if m else None
        if dbu_team_id is None:
            issues.append(
                ParseIssue(
                    sourceUrl=source_url,
                    rowIndex=row_index,
                    rawRow=str(team_div)[:200],
                    reason=f"could not extract dbuTeamId for team {name_text!r}",
                    severity=ParseIssueSeverity.WARNING,
                )
            )

        stadium_div = team_div.find("div", class_="sr--pool--team-list--team--stadium")
        stadium_name = None
        if stadium_div is not None:
            direct_text_nodes = stadium_div.find_all(string=True, recursive=False)
            stadium_name = "".join(direct_text_nodes).strip() or None

        # Deliberately no read of .sr--pool--team-list--team--coach — see
        # module docstring (C6/N4).

        entries.append(
            TeamRosterEntry(
                dbuTeamId=dbu_team_id,
                displayName=name_text,
                stadiumName=stadium_name,
            )
        )

    return entries, issues
