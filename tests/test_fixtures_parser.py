"""dkfr.parse.fixtures tests against SYNTHETIC HTML fixtures (never real
scraped DBU content — tests/fixtures/html/*.html are hand-authored, see
Risk R-6 in the design)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from dkfr.parse.fixtures import extract_team_ids, parse_fixtures
from dkfr.vocab import MatchStatus

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "html"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_basic_kampprogram_parses_played_and_unplayed():
    html = _load("kampprogram_basic.html")
    matches, issues = parse_fixtures(html, "https://example.test/basic")

    assert issues == []
    assert len(matches) == 2  # the "adtr" ad row must be skipped entirely

    played = matches[0]
    assert played.matchNumber == "100001"
    assert played.date == date(2025, 8, 9)
    assert played.homeTeamName == "Test FC A"
    assert played.awayTeamName == "Test FC B"
    assert played.homeGoals == 4
    assert played.awayGoals == 2
    assert played.status == MatchStatus.PLAYED
    assert played.venueName == "Test Arena"
    assert played.matchIdFromUrl == "100001"

    unplayed = matches[1]
    assert unplayed.homeGoals is None
    assert unplayed.awayGoals is None
    assert unplayed.status == MatchStatus.NOT_PLAYED
    assert unplayed.venueName is None
    assert unplayed.kickoffTime is None


def test_extract_team_ids():
    html = _load("kampprogram_basic.html")
    matches, _ = parse_fixtures(html, "https://example.test/basic")
    home_id, away_id = extract_team_ids(matches[0])
    assert home_id == "1001"
    assert away_id == "1002"


def test_tv_column_pulje_does_not_misread_venue_as_broadcaster():
    """Regression test for the real bug found in T6: a fixed offset-from-the-
    end extractor reads "TV3 Sport" as the venue and the away team name as
    the venue when a TV column is present. Header-text-driven extraction
    must get every field right regardless of the extra column."""
    html = _load("kampprogram_tv_column.html")
    matches, issues = parse_fixtures(html, "https://example.test/tv")

    assert issues == []
    assert len(matches) == 1
    m = matches[0]
    assert m.homeTeamName == "Viborg"
    assert "benhavn" in m.awayTeamName.lower()
    assert m.venueName == "Energi Viborg Arena"
    assert m.homeGoals == 2
    assert m.awayGoals == 3


def test_penalty_badge_on_away_side_digit_before_badge():
    html = _load("kampprogram_penalties.html")
    matches, issues = parse_fixtures(html, "https://example.test/penalties")
    assert issues == []
    m = matches[0]
    assert m.homeGoals == 2
    assert m.awayGoals == 2
    assert m.penaltyHomeGoals == 4
    assert m.penaltyAwayGoals == 5
    assert m.status == MatchStatus.PLAYED


def test_penalty_badge_on_home_side_digit_after_badge():
    """Regression test for the real bug found in T6: when the penalty badge
    is nested INSIDE .home-score with the goal-count text node AFTER the
    badge div (not before, as in the other fixture), get_text() on the div
    interleaves the badge's tooltip text with the digit and produces a
    non-numeric string. direct_text() must isolate the real digit
    regardless of the badge's position in the DOM."""
    html = _load("kampprogram_penalties.html")
    matches, issues = parse_fixtures(html, "https://example.test/penalties")
    assert issues == []
    m = matches[1]
    assert m.homeGoals == 1
    assert m.awayGoals == 1
    assert m.penaltyHomeGoals == 4
    assert m.penaltyAwayGoals == 2
    assert m.status == MatchStatus.PLAYED


def test_no_table_produces_error_issue():
    matches, issues = parse_fixtures("<html><body>no table here</body></html>", "https://x")
    assert matches == []
    assert len(issues) == 1
    assert issues[0].severity == "ERROR"
