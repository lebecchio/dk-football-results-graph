"""Parse a `stillingFuld` page into standings rows.

Confirmed structure (docs/specs/dk-results-scraper/discovery-notes.md): a
two-row `<thead>` — a grouping row ("Hjemme"/"Ude" spanning 4 columns each)
and a sub-header row with the actual repeated column labels (`V, U, T,
Score` for home, then again for away, then `K, Score, P`). Because `V`/`U`/
`T`/`Score` each appear twice, true header-*name*-driven lookup is
impossible without the grouping row's colspans — so this parser validates
the exact confirmed 14-column sub-header shape and fails loudly (an
error-severity ParseIssue, not a silent misread) if a pulje's standings
table doesn't match it, rather than guessing positions.

Data row shape (confirmed, Herre-DS Pulje 4 rank 1):
rank, teamName, homeWon, homeDrawn, homeLost, homeGoals("F-A"), awayWon,
awayDrawn, awayLost, awayGoals("F-A"), played(K), totalGoals("F-A"),
points(P), <trailing empty>.
"""

from __future__ import annotations

from pydantic import BaseModel

from dkfr.parse.issues import ParseIssue
from dkfr.parse.tables import cell_link, cell_text, extract_team_id, parse_html
from dkfr.parse.values import parse_score
from dkfr.vocab import ParseIssueSeverity

EXPECTED_SUBHEADER = ["", "", "V", "U", "T", "Score", "V", "U", "T", "Score", "K", "Score", "P", ""]


class StandingRow(BaseModel):
    rank: int
    teamName: str
    teamHref: str | None
    teamId: str | None
    homeWon: int
    homeDrawn: int
    homeLost: int
    homeGoalsFor: int
    homeGoalsAgainst: int
    awayWon: int
    awayDrawn: int
    awayLost: int
    awayGoalsFor: int
    awayGoalsAgainst: int
    played: int
    totalGoalsFor: int
    totalGoalsAgainst: int
    points: int


def _split_goals(text: str) -> tuple[int, int] | None:
    """Standings goal cells use the same "F-A" shape as match scores
    (confirmed same separator-format tolerance needed — C8 applies here
    too), so this reuses parse_score directly."""
    return parse_score(text)


def parse_standings(html: str, source_url: str) -> tuple[list[StandingRow], list[ParseIssue]]:
    soup = parse_html(html)
    tables = soup.find_all("table")
    if not tables:
        return [], [
            ParseIssue(
                sourceUrl=source_url,
                rowIndex=-1,
                rawRow="<no table found>",
                reason="stillingFuld page has no <table> element",
                severity=ParseIssueSeverity.ERROR,
            )
        ]

    table = tables[0]
    thead = table.find("thead")
    if thead is None:
        return [], [
            ParseIssue(
                sourceUrl=source_url,
                rowIndex=-1,
                rawRow="<no thead>",
                reason="stillingFuld table has no <thead>",
                severity=ParseIssueSeverity.ERROR,
            )
        ]

    header_rows = thead.find_all("tr")
    if len(header_rows) < 2:
        return [], [
            ParseIssue(
                sourceUrl=source_url,
                rowIndex=-1,
                rawRow=str(thead),
                reason=f"expected a 2-row thead, found {len(header_rows)}",
                severity=ParseIssueSeverity.ERROR,
            )
        ]

    subheader_texts = [th.get_text(strip=True) for th in header_rows[1].find_all("th")]
    if subheader_texts != EXPECTED_SUBHEADER:
        return [], [
            ParseIssue(
                sourceUrl=source_url,
                rowIndex=-1,
                rawRow=" | ".join(subheader_texts),
                reason=(
                    f"stillingFuld sub-header {subheader_texts!r} does not match the "
                    f"confirmed shape {EXPECTED_SUBHEADER!r} — column positions can't "
                    "be trusted, refusing to guess"
                ),
                severity=ParseIssueSeverity.ERROR,
            )
        ]

    tbody = table.find("tbody")
    data_rows = tbody.find_all("tr") if tbody else header_rows[2:]

    rows: list[StandingRow] = []
    issues: list[ParseIssue] = []

    for row_index, row in enumerate(data_rows, start=1):
        cells = row.find_all("td")
        raw_row_text = " | ".join(cell_text(c) for c in cells)
        if len(cells) != len(EXPECTED_SUBHEADER):
            issues.append(
                ParseIssue(
                    sourceUrl=source_url,
                    rowIndex=row_index,
                    rawRow=raw_row_text,
                    reason=f"expected {len(EXPECTED_SUBHEADER)} cells, got {len(cells)}",
                    severity=ParseIssueSeverity.ERROR,
                )
            )
            continue

        rank_text = cell_text(cells[0])
        team_cell = cells[1]
        team_name = cell_text(team_cell)
        team_href = cell_link(team_cell)
        team_id = extract_team_id(team_href)

        try:
            rank = int(rank_text)
            home_won = int(cell_text(cells[2]))
            home_drawn = int(cell_text(cells[3]))
            home_lost = int(cell_text(cells[4]))
            home_goals = _split_goals(cell_text(cells[5]))
            away_won = int(cell_text(cells[6]))
            away_drawn = int(cell_text(cells[7]))
            away_lost = int(cell_text(cells[8]))
            away_goals = _split_goals(cell_text(cells[9]))
            played = int(cell_text(cells[10]))
            total_goals = _split_goals(cell_text(cells[11]))
            points = int(cell_text(cells[12]))
        except ValueError as exc:
            issues.append(
                ParseIssue(
                    sourceUrl=source_url,
                    rowIndex=row_index,
                    rawRow=raw_row_text,
                    reason=f"non-numeric cell in standings row: {exc}",
                    severity=ParseIssueSeverity.ERROR,
                )
            )
            continue

        if home_goals is None or away_goals is None or total_goals is None:
            issues.append(
                ParseIssue(
                    sourceUrl=source_url,
                    rowIndex=row_index,
                    rawRow=raw_row_text,
                    reason="unparseable goals-for/against cell (expected 'F-A' shape)",
                    severity=ParseIssueSeverity.ERROR,
                )
            )
            continue

        rows.append(
            StandingRow(
                rank=rank,
                teamName=team_name,
                teamHref=team_href,
                teamId=team_id,
                homeWon=home_won,
                homeDrawn=home_drawn,
                homeLost=home_lost,
                homeGoalsFor=home_goals[0],
                homeGoalsAgainst=home_goals[1],
                awayWon=away_won,
                awayDrawn=away_drawn,
                awayLost=away_lost,
                awayGoalsFor=away_goals[0],
                awayGoalsAgainst=away_goals[1],
                played=played,
                totalGoalsFor=total_goals[0],
                totalGoalsAgainst=total_goals[1],
                points=points,
            )
        )

    return rows, issues
