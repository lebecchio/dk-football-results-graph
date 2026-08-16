"""dkfr.parse.standings tests against synthetic HTML fixtures."""

from __future__ import annotations

from pathlib import Path

from dkfr.parse.standings import parse_standings

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "html"


def test_basic_stillingfuld_parses_both_rows():
    html = (FIXTURES_DIR / "stillingfuld_basic.html").read_text(encoding="utf-8")
    rows, issues = parse_standings(html, "https://example.test/stilling")

    assert issues == []
    assert len(rows) == 2

    top = rows[0]
    assert top.rank == 1
    assert top.teamName == "Test Top FC"
    assert top.teamId == "9001"
    assert top.homeWon == 8
    assert top.homeDrawn == 1
    assert top.homeLost == 0
    assert top.homeGoalsFor == 29
    assert top.homeGoalsAgainst == 8
    assert top.awayGoalsFor == 25
    assert top.awayGoalsAgainst == 12
    assert top.played == 18
    assert top.totalGoalsFor == 54
    assert top.totalGoalsAgainst == 20
    assert top.points == 45

    bottom = rows[1]
    assert bottom.teamId == "9002"
    assert bottom.points == 19


def test_no_table_produces_error_issue():
    rows, issues = parse_standings("<html><body>empty</body></html>", "https://x")
    assert rows == []
    assert len(issues) == 1
    assert issues[0].severity == "ERROR"


def test_unexpected_subheader_shape_fails_loudly_not_silently():
    html = """
    <table><thead>
      <tr><th>Group</th></tr>
      <tr><th>Unexpected</th><th>Shape</th></tr>
    </thead><tbody></tbody></table>
    """
    rows, issues = parse_standings(html, "https://x")
    assert rows == []
    assert len(issues) == 1
    assert "does not match" in issues[0].reason
