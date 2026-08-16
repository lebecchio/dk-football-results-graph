"""Direct unit tests for the low-level extraction helpers in dkfr.parse.tables."""

from __future__ import annotations

from dkfr.parse.tables import (
    cell_link,
    desktop_cells,
    direct_text,
    extract_match_id,
    extract_team_id,
    parse_html,
    row_link,
)


def test_desktop_cells_excludes_only_on_mobile():
    html = """
    <tr>
      <td class="hide-on-mobile">A</td>
      <td class="hide-on-mobile">B</td>
      <td class="only-on-mobile">MOBILE DUPLICATE A B</td>
    </tr>
    """
    soup = parse_html(html)
    row = soup.find("tr")
    cells = desktop_cells(row)
    assert len(cells) == 2
    assert [c.get_text(strip=True) for c in cells] == ["A", "B"]


def test_direct_text_ignores_nested_badge():
    html = (
        '<div class="away-score">2<div class="penalty-result-badge">'
        "Straffesparkskonkurrence 4 - 5</div></div>"
    )
    soup = parse_html(html)
    div = soup.find("div", class_="away-score")
    assert direct_text(div) == "2"


def test_direct_text_ignores_nested_badge_when_badge_is_first_child():
    html = (
        '<div class="home-score"><div class="penalty-result-badge">'
        "Straffesparkskonkurrence 4 - 2</div>1</div>"
    )
    soup = parse_html(html)
    div = soup.find("div", class_="home-score")
    assert direct_text(div) == "1"


def test_cell_link_reads_href():
    html = """<td><a href="/resultater/hold/123_456">Team</a></td>"""
    soup = parse_html(html)
    cell = soup.find("td")
    assert cell_link(cell) == "/resultater/hold/123_456"


def test_cell_link_reads_onclick_on_cell_itself():
    html = """<td onclick="window.location = '/resultater/hold/123_456/kampprogram'">Team</td>"""
    soup = parse_html(html)
    cell = soup.find("td")
    assert cell_link(cell) == "/resultater/hold/123_456/kampprogram"


def test_row_link_reads_window_location_onclick():
    # row_link is for the window.location-assignment pattern (holdoversigt,
    # multi-pulje Raekke pages) — the MatchProgramMatchClick(...) pattern
    # used on kampprogramFuld rows is read directly via extract_match_id in
    # fixtures.py instead, since it's a function call, not an assignment.
    html = """<tr onclick="window.location = '/resultater/pulje/473829/'"></tr>"""
    soup = parse_html(html)
    row = soup.find("tr")
    assert row_link(row) == "/resultater/pulje/473829/"


def test_extract_team_id():
    assert extract_team_id("/resultater/hold/12963_473829") == "12963"
    assert extract_team_id(None) is None
    assert extract_team_id("/resultater/pulje/473829") is None


def test_extract_match_id():
    assert extract_match_id("/resultater/kamp/909802_473829/kampinfo") == "909802"
    assert extract_match_id(None) is None
