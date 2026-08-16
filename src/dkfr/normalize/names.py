"""Name normalization: Unicode/whitespace cleanup, squad-ordinal splitting,
and slug generation for club grouping (design Decision 3).
"""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE_RE = re.compile(r"\s+")

# "AaB 2" / "B 93 (2)" / "Brøndby IF II" -> (base name, squad index).
# squadIndex is None for a first/only team.
_SQUAD_ORDINAL_RE = re.compile(
    r"^(?P<base>.+?)\s*(?:\((?P<paren_num>\d+)\)|(?P<trail_num>\d+)|(?P<roman>I{1,3}|IV))\s*$"
)
_ROMAN_MAP = {"I": 2, "II": 2, "III": 3, "IV": 4}

DANISH_TRANSLITERATION = str.maketrans(
    {"æ": "ae", "ø": "oe", "å": "aa", "Æ": "Ae", "Ø": "Oe", "Å": "Aa"}
)


def normalize_display_name(text: str) -> str:
    """NFC-normalize, strip, and collapse internal whitespace. Preserves the
    display form verbatim otherwise (casing, Danish letters) — this is what
    gets stored as the human-facing name; casefold/slug happen separately."""
    text = unicodedata.normalize("NFC", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def split_squad_ordinal(name: str) -> tuple[str, int | None]:
    """Split a reserve/second-team suffix off a display name.

    "AaB 2" -> ("AaB", 2); "B 93 (2)" -> ("B 93", 2); "Brøndby IF II" ->
    ("Brøndby IF", 2); "FC København" -> ("FC København", None).

    Not observed in the T3 sample (all top-tier national puljer — see
    discovery-notes.md), but built per the design regardless, since 3.
    Division / Danmarksserien (in the full manifest) are exactly where
    reserve teams are plausible.
    """
    name = normalize_display_name(name)
    m = _SQUAD_ORDINAL_RE.match(name)
    if not m:
        return name, None

    base = m.group("base").strip()
    if not base:
        # The whole string was just a number/roman numeral — not a real
        # squad-ordinal case, treat as unsplit.
        return name, None

    if m.group("paren_num"):
        idx = int(m.group("paren_num"))
    elif m.group("trail_num"):
        idx = int(m.group("trail_num"))
        # Guard against false positives like a club literally named "B 93" —
        # only split trailing bare numbers that look like a squad ordinal
        # (small, 2-9), not a club name that happens to end in a number.
        if not (2 <= idx <= 9):
            return name, None
    else:
        idx = _ROMAN_MAP.get(m.group("roman"))
        if idx is None:
            return name, None
        # A bare "I" is far too ambiguous (many valid club-name endings) to
        # treat as a squad ordinal — require II/III/IV.
        if m.group("roman") == "I":
            return name, None

    return base, idx


def slugify(text: str) -> str:
    """Lowercase, transliterate Danish letters, strip punctuation, hyphenate.
    Used for the default clubId derivation (design Decision 3's "Default:
    clubId = slug(canonicalTeamName with squad ordinal stripped)")."""
    text = normalize_display_name(text)
    text = text.translate(DANISH_TRANSLITERATION)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")
