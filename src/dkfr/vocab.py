"""Shared enum vocabulary for the whole pipeline.

Every module that touches phase/bracket/gender/etc. imports from here —
manifest, parser, normalized records, loader, and the docs in
docs/schema/model.md all must agree with this single source. A drifted
string literal between the parser and the loader is the most likely
silent-corruption bug in this project (see design.md "Workstream split").
"""

from __future__ import annotations

from enum import Enum


class Gender(str, Enum):
    MEN = "MEN"
    WOMEN = "WOMEN"


class AgeBracket(str, Enum):
    SENIOR = "SENIOR"
    U19 = "U19"
    U17 = "U17"
    U16 = "U16"


class Bracket(str, Enum):
    """Mechanically derived from (gender, ageBracket) — see design.md Decision 1."""

    MEN_SENIOR = "MEN_SENIOR"
    WOMEN_SENIOR = "WOMEN_SENIOR"
    MEN_U19 = "MEN_U19"
    MEN_U17 = "MEN_U17"
    WOMEN_U19 = "WOMEN_U19"
    WOMEN_U16 = "WOMEN_U16"


# (gender, ageBracket) -> bracket, the single mapping every module must use.
BRACKET_MAP: dict[tuple[Gender, AgeBracket], Bracket] = {
    (Gender.MEN, AgeBracket.SENIOR): Bracket.MEN_SENIOR,
    (Gender.WOMEN, AgeBracket.SENIOR): Bracket.WOMEN_SENIOR,
    (Gender.MEN, AgeBracket.U19): Bracket.MEN_U19,
    (Gender.MEN, AgeBracket.U17): Bracket.MEN_U17,
    (Gender.WOMEN, AgeBracket.U19): Bracket.WOMEN_U19,
    (Gender.WOMEN, AgeBracket.U16): Bracket.WOMEN_U16,
}


def derive_bracket(gender: Gender, age_bracket: AgeBracket) -> Bracket:
    key = (gender, age_bracket)
    if key not in BRACKET_MAP:
        raise ValueError(f"No bracket defined for (gender={gender}, ageBracket={age_bracket})")
    return BRACKET_MAP[key]


class Phase(str, Enum):
    GRUNDSPIL = "GRUNDSPIL"
    MESTERSKABSSPIL = "MESTERSKABSSPIL"
    OPRYKNINGSSPIL = "OPRYKNINGSSPIL"
    NEDRYKNINGSSPIL = "NEDRYKNINGSSPIL"
    KVALIFIKATIONSSPIL = "KVALIFIKATIONSSPIL"
    SINGLE = "SINGLE"
    CUP = "CUP"  # reserved, unused in v1 — see spec N8 / design OQ-2


class Administrator(str, Enum):
    DBU = "DBU"
    DIVISIONSFORENINGEN = "DIVISIONSFORENINGEN"


class Side(str, Enum):
    HOME = "HOME"
    AWAY = "AWAY"


class Outcome(str, Enum):
    WIN = "WIN"
    DRAW = "DRAW"
    LOSS = "LOSS"
    UNKNOWN = "UNKNOWN"  # not-played / no result yet


class MatchStatus(str, Enum):
    PLAYED = "PLAYED"
    NOT_PLAYED = "NOT_PLAYED"
    POSTPONED = "POSTPONED"
    ABANDONED = "ABANDONED"
    ANNULLED = "ANNULLED"
    WALKOVER = "WALKOVER"
    UNKNOWN = "UNKNOWN"


class ParseIssueSeverity(str, Enum):
    WARNING = "WARNING"
    ERROR = "ERROR"
