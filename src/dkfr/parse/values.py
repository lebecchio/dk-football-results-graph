"""Tolerant scalar parsers for the values embedded in DBU's pulje tables.

Every function here is a pure function: raw text (or a small tuple of raw
texts) in, a parsed value or `None` out. Nothing here touches the network
or the DOM — see parse/tables.py and parse/fixtures.py for the structural
extraction that feeds these. This is deliberately the highest-value unit
test surface in the project (spec R2.9/C8) — every format variation
confirmed in docs/specs/dk-results-scraper/discovery-notes.md is covered
by a test in tests/test_values.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from dkfr.vocab import MatchStatus

COPENHAGEN = ZoneInfo("Europe/Copenhagen")

# --- score ---

# Accepts "2 - 2", "4-2", "2–2" (en dash), "2 : 2". Whitespace around the
# separator is optional and tolerated either side (spec C8).
_SCORE_RE = re.compile(r"^\s*(\d+)\s*[-–:]\s*(\d+)\s*$")


def parse_score(text: str | None) -> tuple[int, int] | None:
    """Parse a combined "H-A" style score string. Returns None if the text
    doesn't look like a played score (empty, a dash placeholder, or a status
    marker) — callers should fall back to parse_status for those cases."""
    if text is None:
        return None
    stripped = text.strip()
    if not stripped or stripped == "-":
        return None
    m = _SCORE_RE.match(stripped)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def parse_score_sides(home_text: str | None, away_text: str | None) -> tuple[int, int] | None:
    """Parse already-split home/away score strings (the structured extraction
    path — see discovery-notes.md: real markup exposes .home-score/.away-score
    as separate elements, which is a more reliable source than splitting a
    concatenated "4-2" cell). Each side's text may carry trailing whitespace
    or nested badge text (e.g. a penalty badge's digits) — only the LEADING
    integer of each side is taken."""
    if home_text is None or away_text is None:
        return None
    home_stripped = home_text.strip()
    away_stripped = away_text.strip()
    if not home_stripped or not away_stripped:
        return None
    home_m = re.match(r"^(\d+)", home_stripped)
    away_m = re.match(r"^(\d+)", away_stripped)
    if not home_m or not away_m:
        return None
    return int(home_m.group(1)), int(away_m.group(1))


# --- penalties ---

# "Straffesparkskonkurrence 4 - 5" or "Straffesparkskonkurrence\n4 - 5" (the
# real markup separates the label and the score with a <br/>, i.e. a newline
# once BeautifulSoup's get_text(separator="\n") is used — see
# discovery-notes.md "Where does the penalty text live?").
_PENALTY_RE = re.compile(
    r"straffesparkskonkurrence\s*[\n:]*\s*(\d+)\s*[-–:]\s*(\d+)", re.IGNORECASE
)


def parse_penalties(text: str | None) -> tuple[int, int] | None:
    """Parse a penalty-shootout result from free text containing the
    "Straffesparkskonkurrence" label (confirmed the only marker observed —
    discovery-notes.md). Scans the whole input, so it's safe to pass either
    just the tooltip text or the entire result cell's text (design's T5 note:
    "must scan both the result cell's full text and any trailing sibling
    cell" — this handles both by being scan-based, not position-based)."""
    if not text:
        return None
    m = _PENALTY_RE.search(text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


# --- status ---

# Confirmed markers per the design's anticipated vocabulary (spec R1);
# NOT empirically observed in the T3 sample (season was 100% played through
# in every sampled pulje — discovery-notes.md). Implemented defensively so
# the full T6 fetch across ~31 puljer can exercise real examples if any
# exist, and anything outside this vocabulary is reported (AC11), not
# silently guessed.
_STATUS_MARKERS: list[tuple[str, MatchStatus]] = [
    ("ikke afviklet", MatchStatus.NOT_PLAYED),
    ("udsat", MatchStatus.POSTPONED),
    ("afbrudt", MatchStatus.ABANDONED),
    ("annulleret", MatchStatus.ANNULLED),
    ("walkover", MatchStatus.WALKOVER),
    ("wo", MatchStatus.WALKOVER),
]


def parse_status(result_text: str | None) -> tuple[MatchStatus, bool]:
    """Determine match status from the raw result-cell text.

    Returns (status, recognized). `recognized=False` means the text was
    non-empty but matched neither a parseable score nor a known marker —
    callers must raise an error-severity ParseIssue for this case (AC11),
    never silently default to a guessed status.
    """
    if result_text is None or not result_text.strip():
        return MatchStatus.NOT_PLAYED, True

    if parse_score(result_text) is not None:
        return MatchStatus.PLAYED, True

    lowered = result_text.strip().lower()
    for marker, status in _STATUS_MARKERS:
        if marker == lowered or marker in lowered:
            return status, True

    return MatchStatus.UNKNOWN, False


# --- date / time ---

_WEEKDAY_MAP = {
    "man": 0,
    "tir": 1,
    "ons": 2,
    "tor": 3,
    "fre": 4,
    "lør": 5,
    "søn": 6,
}

# "lør.09-08 2025" — weekday abbrev + "." + DD-MM + " " + YYYY (confirmed
# format, discovery-notes.md).
_DATE_RE = re.compile(
    r"^\s*(?P<weekday>man|tir|ons|tor|fre|lør|søn)\.\s*"
    r"(?P<day>\d{2})-(?P<month>\d{2})\s+(?P<year>\d{4})\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DateParseResult:
    date: date
    weekday_mismatch: bool  # True if the stated weekday != the computed one


def parse_danish_date(text: str | None) -> DateParseResult | None:
    """Parse "lør.09-08 2025" -> DateParseResult(date(2025, 8, 9), False).

    Cross-checks the stated weekday abbreviation against the weekday computed
    from the parsed date — a free correctness check the design calls for
    explicitly. A mismatch does not fail parsing (the date itself is still
    usable) but is flagged via `weekday_mismatch` so the caller can raise a
    warning-severity ParseIssue.
    """
    if text is None:
        return None
    m = _DATE_RE.match(text)
    if not m:
        return None
    day = int(m.group("day"))
    month = int(m.group("month"))
    year = int(m.group("year"))
    try:
        parsed_date = date(year, month, day)
    except ValueError:
        return None
    stated_weekday = _WEEKDAY_MAP[m.group("weekday").lower()]
    mismatch = parsed_date.weekday() != stated_weekday
    return DateParseResult(date=parsed_date, weekday_mismatch=mismatch)


_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")


def parse_time(text: str | None) -> time | None:
    """Parse "13:00" -> time(13, 0). Returns None for missing/unparseable
    kickoff times (nullable per spec R1)."""
    if text is None:
        return None
    m = _TIME_RE.match(text)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)


def to_instant(local_date: date, local_time: time | None) -> datetime | None:
    """Combine a local Europe/Copenhagen date + time into a UTC instant.

    Returns None when there's no kickoff time to anchor to — a bare date
    with no time is not converted to a fabricated midnight instant, since
    that would silently imply a false precision. Both the local `date` and
    this UTC `kickoffAt` are kept on the record (design's Match schema) —
    the season spans a DST boundary (spec R-10), so deriving "which
    matchday" from the UTC instant alone would be fragile.
    """
    if local_time is None:
        return None
    local_dt = datetime.combine(local_date, local_time, tzinfo=COPENHAGEN)
    return local_dt.astimezone(ZoneInfo("UTC"))
