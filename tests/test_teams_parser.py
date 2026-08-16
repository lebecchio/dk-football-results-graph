"""dkfr.parse.teams tests against synthetic HTML fixtures. Also asserts the
privacy guardrail (spec C6/N4): coach names must never be extracted."""

from __future__ import annotations

from pathlib import Path

from dkfr.parse.teams import parse_teams

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "html"


def test_basic_holdoversigt_parses_both_teams():
    html = (FIXTURES_DIR / "holdoversigt_basic.html").read_text(encoding="utf-8")
    entries, issues = parse_teams(html, "https://example.test/holdoversigt")

    assert issues == []
    assert len(entries) == 2

    assert entries[0].dbuTeamId == "9001"
    assert entries[0].displayName == "Test Top FC"
    assert entries[0].stadiumName == "Test Arena (boldbaner)"

    assert entries[1].dbuTeamId == "9002"
    assert entries[1].displayName == "Test Bottom FC"
    assert entries[1].stadiumName == "Another Ground"


def test_coach_field_is_never_extracted():
    """Privacy guardrail (C6/N4): the coach name present in the fixture must
    not appear anywhere in the parsed output."""
    html = (FIXTURES_DIR / "holdoversigt_basic.html").read_text(encoding="utf-8")
    entries, _ = parse_teams(html, "https://example.test/holdoversigt")

    dumped = [e.model_dump() for e in entries]
    for entry in dumped:
        for value in entry.values():
            assert value != "Should Never Be Extracted"

    # Also confirm TeamRosterEntry has no field capable of carrying it.
    from dkfr.parse.teams import TeamRosterEntry

    assert set(TeamRosterEntry.model_fields) == {"dbuTeamId", "displayName", "stadiumName"}


def test_no_team_entries_produces_error_issue():
    entries, issues = parse_teams("<html><body>empty</body></html>", "https://x")
    assert entries == []
    assert len(issues) == 1
    assert issues[0].severity == "ERROR"
