"""Table-driven tests for dkfr.parse.values — every C8 format variation plus
every T3 discovery finding (docs/specs/dk-results-scraper/discovery-notes.md)."""

from __future__ import annotations

from datetime import date, time

import pytest

from dkfr.parse.values import (
    parse_danish_date,
    parse_penalties,
    parse_score,
    parse_score_sides,
    parse_status,
    parse_time,
    to_instant,
)
from dkfr.vocab import MatchStatus

# --- parse_score ---

SCORE_CASES = [
    ("2 - 2", (2, 2)),
    ("4-2", (4, 2)),
    ("2–2", (2, 2)),  # en dash
    ("2 : 2", (2, 2)),
    ("10-0", (10, 0)),
    ("", None),
    ("-", None),
    (None, None),
    ("Udsat", None),
]


@pytest.mark.parametrize("text,expected", SCORE_CASES)
def test_parse_score(text, expected):
    assert parse_score(text) == expected


def test_parse_score_sides_basic():
    assert parse_score_sides("4", "2") == (4, 2)


def test_parse_score_sides_with_penalty_badge_text():
    # away-score div contains "2" plus nested penalty badge text in real markup;
    # only the leading integer must be taken.
    assert parse_score_sides("2", "2Straffesparkskonkurrence4 - 5") == (2, 2)


def test_parse_score_sides_missing():
    assert parse_score_sides(None, "2") is None
    assert parse_score_sides("", "2") is None


# --- parse_penalties ---


def test_parse_penalties_with_newline_separator():
    text = "Straffesparkskonkurrence\n4 - 5"
    assert parse_penalties(text) == (4, 5)


def test_parse_penalties_with_space_separator():
    text = "Straffesparkskonkurrence 4 - 5"
    assert parse_penalties(text) == (4, 5)


def test_parse_penalties_absent():
    assert parse_penalties("4-2") is None
    assert parse_penalties(None) is None
    assert parse_penalties("") is None


def test_parse_penalties_scans_whole_cell_text():
    # simulates passing the whole result cell's get_text(), not just the tooltip
    text = "2 - 2 Straffesparkskonkurrence\n4 - 5"
    assert parse_penalties(text) == (4, 5)


# --- parse_status ---


def test_parse_status_played():
    status, recognized = parse_status("4-2")
    assert status == MatchStatus.PLAYED
    assert recognized is True


def test_parse_status_not_played_empty():
    status, recognized = parse_status("")
    assert status == MatchStatus.NOT_PLAYED
    assert recognized is True

    status, recognized = parse_status(None)
    assert status == MatchStatus.NOT_PLAYED
    assert recognized is True


@pytest.mark.parametrize(
    "text,expected_status",
    [
        ("Udsat", MatchStatus.POSTPONED),
        ("Afbrudt", MatchStatus.ABANDONED),
        ("Annulleret", MatchStatus.ANNULLED),
        ("Ikke afviklet", MatchStatus.NOT_PLAYED),
        ("Walkover", MatchStatus.WALKOVER),
        ("WO", MatchStatus.WALKOVER),
    ],
)
def test_parse_status_known_markers(text, expected_status):
    status, recognized = parse_status(text)
    assert status == expected_status
    assert recognized is True


def test_parse_status_unrecognized_text_is_not_silently_guessed():
    status, recognized = parse_status("Some new marker DBU invents next season")
    assert status == MatchStatus.UNKNOWN
    assert recognized is False


# --- parse_danish_date ---


def test_parse_danish_date_basic():
    result = parse_danish_date("lør.09-08 2025")
    assert result is not None
    assert result.date == date(2025, 8, 9)
    assert result.weekday_mismatch is False  # 2025-08-09 IS a Saturday


def test_parse_danish_date_friday():
    result = parse_danish_date("fre.15-08 2025")
    assert result is not None
    assert result.date == date(2025, 8, 15)
    assert result.weekday_mismatch is False  # 2025-08-15 IS a Friday


def test_parse_danish_date_weekday_mismatch_detected():
    # 2025-08-09 is actually a Saturday (lør), not a Sunday (søn) — deliberately
    # corrupted input to prove the cross-check fires (design T5 requirement).
    result = parse_danish_date("søn.09-08 2025")
    assert result is not None
    assert result.date == date(2025, 8, 9)
    assert result.weekday_mismatch is True


def test_parse_danish_date_invalid_date_returns_none():
    assert parse_danish_date("lør.31-02 2025") is None  # Feb 31 doesn't exist


def test_parse_danish_date_unparseable_returns_none():
    assert parse_danish_date("not a date") is None
    assert parse_danish_date(None) is None


def test_parse_danish_date_all_weekday_abbreviations():
    # man/tir/ons/tor/fre/lør/søn map to a real week (2025-08-04 is a Monday)
    days = ["man", "tir", "ons", "tor", "fre", "lør", "søn"]
    for i, wd in enumerate(days):
        text = f"{wd}.{4 + i:02d}-08 2025"
        result = parse_danish_date(text)
        assert result is not None, text
        assert result.weekday_mismatch is False, text


# --- parse_time ---


def test_parse_time_basic():
    assert parse_time("13:00") == time(13, 0)
    assert parse_time("09:30") == time(9, 30)


def test_parse_time_missing():
    assert parse_time(None) is None
    assert parse_time("") is None


def test_parse_time_invalid():
    assert parse_time("25:00") is None
    assert parse_time("not a time") is None


# --- to_instant ---


def test_to_instant_summer_cest():
    # 2025-08-09 13:00 local (CEST, UTC+2) -> 11:00 UTC
    instant = to_instant(date(2025, 8, 9), time(13, 0))
    assert instant is not None
    assert instant.hour == 11
    assert instant.utcoffset().total_seconds() == 0


def test_to_instant_winter_cet():
    # A December date is CET (UTC+1) -> 1-hour offset instead of 2
    instant = to_instant(date(2025, 12, 6), time(13, 0))
    assert instant is not None
    assert instant.hour == 12


def test_to_instant_no_time_returns_none():
    assert to_instant(date(2025, 8, 9), None) is None
