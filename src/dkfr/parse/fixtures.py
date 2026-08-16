"""Parse a `kampprogramFuld` page into raw match rows.

Confirmed structure (docs/specs/dk-results-scraper/discovery-notes.md):
one <table>, one <tr> per match with `hide-on-mobile` desktop cells + a
duplicate `only-on-mobile` mobile card, plus assorted non-match rows (ad
placeholders with class "adtr") that must be skipped without becoming parse
issues — they are not malformed match rows, they are not match rows at all.

Column layout is located **by header text, not fixed position** (design's
explicit requirement) — confirmed necessary during T6's full-manifest fetch:
Superliga and other puljer insert an extra "TV" (broadcaster) column between
Spillested and Resultat that Herre-DS/U19/U16-Piger don't have. A
fixed-offset-from-the-end extractor silently reads the wrong column for
those puljer; a header-text map does not.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import time as time_type

from bs4 import Tag
from pydantic import BaseModel

from dkfr.parse.issues import ParseIssue
from dkfr.parse.tables import (
    cell_link,
    cell_text,
    desktop_cells,
    direct_text,
    extract_match_id,
    extract_team_id,
    parse_html,
)
from dkfr.parse.values import (
    parse_danish_date,
    parse_penalties,
    parse_score_sides,
    parse_status,
    parse_time,
)
from dkfr.vocab import MatchStatus, ParseIssueSeverity

REQUIRED_HEADERS = ("Kampnr", "Dato", "Tid", "Hjemme", "Ude", "Spillested", "Resultat")


class RawMatchRow(BaseModel):
    matchNumber: str | None
    dateText: str
    date: date_type | None
    weekdayMismatch: bool
    kickoffTime: time_type | None
    homeTeamName: str
    homeTeamHref: str | None
    awayTeamName: str
    awayTeamHref: str | None
    venueName: str | None
    homeGoals: int | None
    awayGoals: int | None
    penaltyHomeGoals: int | None
    penaltyAwayGoals: int | None
    status: MatchStatus
    matchIdFromUrl: str | None


def _header_index_map(table: Tag, source_url: str) -> tuple[dict[str, int], ParseIssue | None]:
    """Map each REQUIRED_HEADERS name to its column index, read from <thead>."""
    thead = table.find("thead")
    header_cells = thead.find_all("th") if thead else table.find_all("tr")[0].find_all("th")
    header_texts = [c.get_text(strip=True) for c in header_cells]

    index_map: dict[str, int] = {}
    for name in REQUIRED_HEADERS:
        if name in header_texts:
            index_map[name] = header_texts.index(name)

    missing = [name for name in REQUIRED_HEADERS if name not in index_map]
    if missing:
        return index_map, ParseIssue(
            sourceUrl=source_url,
            rowIndex=0,
            rawRow=" | ".join(header_texts),
            reason=f"header row missing expected column(s): {missing}",
            severity=ParseIssueSeverity.ERROR,
        )
    return index_map, None


def _is_match_row(row: Tag, min_cells: int) -> bool:
    classes = row.get("class") or []
    if "adtr" in classes:
        return False
    cells = desktop_cells(row)
    return len(cells) >= min_cells


def parse_fixtures(html: str, source_url: str) -> tuple[list[RawMatchRow], list[ParseIssue]]:
    soup = parse_html(html)
    tables = soup.find_all("table")
    if not tables:
        return [], [
            ParseIssue(
                sourceUrl=source_url,
                rowIndex=-1,
                rawRow="<no table found>",
                reason="kampprogramFuld page has no <table> element",
                severity=ParseIssueSeverity.ERROR,
            )
        ]

    table = tables[0]
    index_map, header_issue = _header_index_map(table, source_url)
    if header_issue is not None:
        return [], [header_issue]

    min_cells = max(index_map.values()) + 1
    all_rows = table.find_all("tr")
    matches: list[RawMatchRow] = []
    issues: list[ParseIssue] = []

    row_index = 0
    for row in all_rows:
        if not _is_match_row(row, min_cells):
            continue
        row_index += 1
        cells = desktop_cells(row)
        raw_row_text = " | ".join(cell_text(c) for c in cells)

        if len(cells) <= max(index_map.values()):
            issues.append(
                ParseIssue(
                    sourceUrl=source_url,
                    rowIndex=row_index,
                    rawRow=raw_row_text,
                    reason=f"expected >= {min_cells} desktop cells, got {len(cells)}",
                    severity=ParseIssueSeverity.ERROR,
                )
            )
            continue

        kampnr_cell = cells[index_map["Kampnr"]]
        date_cell = cells[index_map["Dato"]]
        time_cell = cells[index_map["Tid"]]
        home_cell = cells[index_map["Hjemme"]]
        away_cell = cells[index_map["Ude"]]
        venue_cell = cells[index_map["Spillested"]]
        result_cell = cells[index_map["Resultat"]]

        kampnr_text = cell_text(kampnr_cell)
        match_number = kampnr_text if kampnr_text and kampnr_text.isdigit() else None

        date_text = cell_text(date_cell)
        date_result = parse_danish_date(date_text)
        if date_result is None:
            issues.append(
                ParseIssue(
                    sourceUrl=source_url,
                    rowIndex=row_index,
                    rawRow=raw_row_text,
                    reason=f"unparseable date text {date_text!r}",
                    severity=ParseIssueSeverity.ERROR,
                )
            )
            parsed_date = None
            weekday_mismatch = False
        else:
            parsed_date = date_result.date
            weekday_mismatch = date_result.weekday_mismatch
            if weekday_mismatch:
                issues.append(
                    ParseIssue(
                        sourceUrl=source_url,
                        rowIndex=row_index,
                        rawRow=raw_row_text,
                        reason=(
                            f"stated weekday does not match computed weekday for {date_text!r}"
                        ),
                        severity=ParseIssueSeverity.WARNING,
                    )
                )

        kickoff_time = parse_time(cell_text(time_cell))

        home_name = cell_text(home_cell)
        away_name = cell_text(away_cell)
        home_href = cell_link(home_cell)
        away_href = cell_link(away_cell)

        venue_text = cell_text(venue_cell)
        venue_name = venue_text or None

        home_score_div = result_cell.find("div", class_="home-score")
        away_score_div = result_cell.find("div", class_="away-score")
        result_full_text = cell_text(result_cell)

        home_goals = away_goals = None
        if home_score_div is not None and away_score_div is not None:
            score = parse_score_sides(direct_text(home_score_div), direct_text(away_score_div))
            if score is not None:
                home_goals, away_goals = score

        if home_goals is not None and away_goals is not None:
            status = MatchStatus.PLAYED
        else:
            status, recognized = parse_status(result_full_text)
            if not recognized:
                issues.append(
                    ParseIssue(
                        sourceUrl=source_url,
                        rowIndex=row_index,
                        rawRow=raw_row_text,
                        reason=(
                            f"unrecognized result text {result_full_text!r} — not a "
                            "score, not a known status marker"
                        ),
                        severity=ParseIssueSeverity.ERROR,
                    )
                )

        penalties = parse_penalties(result_full_text)
        pen_home, pen_away = penalties if penalties else (None, None)

        row_onclick = row.get("onclick") or ""
        match_id = extract_match_id(row_onclick)

        matches.append(
            RawMatchRow(
                matchNumber=match_number,
                dateText=date_text,
                date=parsed_date,
                weekdayMismatch=weekday_mismatch,
                kickoffTime=kickoff_time,
                homeTeamName=home_name,
                homeTeamHref=home_href,
                awayTeamName=away_name,
                awayTeamHref=away_href,
                venueName=venue_name,
                homeGoals=home_goals,
                awayGoals=away_goals,
                penaltyHomeGoals=pen_home,
                penaltyAwayGoals=pen_away,
                status=status,
                matchIdFromUrl=match_id,
            )
        )

    return matches, issues


def extract_team_ids(row: RawMatchRow) -> tuple[str | None, str | None]:
    return extract_team_id(row.homeTeamHref), extract_team_id(row.awayTeamHref)
