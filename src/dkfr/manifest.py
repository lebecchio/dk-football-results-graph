"""The manifest: pydantic models, loader, referential checks, and `verify`.

manifest/puljer.yaml is the hand-curated, checked-in seed list of DBU pulje
IDs (spec R2.1) — the primary discovery mechanism, since there is no
robots-permitted way to enumerate puljer mechanically at request time (see
docs/specs/dk-results-scraper/discovery-notes.md Finding 0 for how this
particular manifest's IDs were actually resolved: the /resultater/raekkesoeg/
+ /resultater/Raekke/<id> redirect mechanism, not guesswork).

This module owns:
- The pydantic schema for the two top-level YAML sections (competitions,
  puljer).
- Referential integrity checks (every pulje.competitionId must resolve).
- `verify_manifest()` — AC1: fetch each pulje's landing page and assert its
  title matches the declared competition/phase/group/season.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from dkfr.vocab import Administrator, AgeBracket, Bracket, Gender, Phase, derive_bracket

# Danish phase labels as they appear in real pulje/Raekke titles — confirmed
# empirically in discovery-notes.md (Finding "Exact pulje-title format").
PHASE_LABEL_DA: dict[Phase, str | None] = {
    Phase.GRUNDSPIL: "Grundspil",
    Phase.MESTERSKABSSPIL: "Mesterskabsspil",
    Phase.OPRYKNINGSSPIL: "Oprykningsspil",
    Phase.NEDRYKNINGSSPIL: "Nedrykningsspil",
    Phase.KVALIFIKATIONSSPIL: "Kvalifikationsspil",
    Phase.SINGLE: None,  # no phase suffix expected in the title
    Phase.CUP: None,
}

SEASON_CODE = "2026"  # the site's season-selector value for 2025/26 (spec F11)


class CompetitionEntry(BaseModel):
    name: str
    bracket: Bracket
    gender: Gender
    ageBracket: AgeBracket
    tier: int = Field(ge=1)
    administrator: Administrator

    @model_validator(mode="after")
    def _bracket_matches_gender_age(self) -> CompetitionEntry:
        expected = derive_bracket(self.gender, self.ageBracket)
        if expected != self.bracket:
            raise ValueError(
                f"competition {self.name!r}: declared bracket {self.bracket} does not "
                f"match derive_bracket(gender={self.gender}, ageBracket={self.ageBracket}) "
                f"= {expected}"
            )
        return self


class PuljeEntry(BaseModel):
    puljeId: int
    competitionId: str
    phase: Phase
    groupLabel: str | None = None
    pointsCarryOver: bool = False
    expectedTeams: int | None = None
    expectedMatches: int | None = None
    note: str | None = None
    # For the rare pulje whose real page title doesn't contain the parent
    # competition's registered name (observed once: "Oprykningskampe fra DS",
    # a Herre-DS <-> 3. Division cross-tier playoff titled without "Herre-DS"
    # at all) — overrides the name used by check_pulje_title's name match.
    nameOverride: str | None = None

    @field_validator("puljeId")
    @classmethod
    def _positive_id(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("puljeId must be positive")
        return v


class Manifest(BaseModel):
    competitions: dict[str, CompetitionEntry]
    puljer: list[PuljeEntry]

    @model_validator(mode="after")
    def _referential_integrity(self) -> Manifest:
        unknown = {p.competitionId for p in self.puljer} - set(self.competitions)
        if unknown:
            raise ValueError(f"puljer reference unknown competitionId(s): {sorted(unknown)}")
        dupe_ids = [p.puljeId for p in self.puljer]
        seen = set()
        dupes = set()
        for pid in dupe_ids:
            if pid in seen:
                dupes.add(pid)
            seen.add(pid)
        if dupes:
            raise ValueError(f"duplicate puljeId(s) in manifest: {sorted(dupes)}")
        return self

    def competition_for(self, pulje: PuljeEntry) -> CompetitionEntry:
        return self.competitions[pulje.competitionId]


def load_manifest(path: Path) -> Manifest:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Manifest.model_validate(raw)


# --- verify() ---


class VerifyResult(BaseModel):
    puljeId: int
    competitionId: str
    ok: bool
    fetchFailed: bool = False
    fetchedTitle: str | None = None
    reason: str | None = None
    url: str | None = None


def _title_from_html(html: str) -> str | None:
    m = re.search(r"<h2>([^<]*)</h2>", html)
    if m:
        return m.group(1).strip()
    return None


def check_pulje_title(
    title: str | None, competition: CompetitionEntry, pulje: PuljeEntry
) -> str | None:
    """Return None if `title` is consistent with the declared manifest entry,
    otherwise a human-readable reason string."""
    if title is None:
        return "no <h2> title found on the fetched page"

    if SEASON_CODE not in title:
        return f"title {title!r} does not contain season code {SEASON_CODE!r}"

    # Competition name match is intentionally loose (substring, case-insensitive,
    # and tolerant of the sponsor-prefix churn DBU does every season — e.g.
    # "3F Superliga" / "CampoBet 3. Division" / "Betinia LIGA"). We accept a
    # match against the full declared name OR the name with its leading
    # (likely-sponsor) word stripped, so "2. Division" and "3. Division" are
    # still distinguished from each other even though both end in "Division".
    # `nameOverride` handles the rare pulje whose title doesn't contain the
    # competition's registered name at all (see PuljeEntry docstring).
    name = pulje.nameOverride or competition.name
    words = name.split()
    candidates = [name]
    if len(words) > 1:
        candidates.append(" ".join(words[1:]))
    title_lower = title.lower()
    if not any(c.lower() in title_lower for c in candidates):
        return f"title {title!r} matches none of {candidates!r}"

    # A pulje is uniquely identified by its phase label OR its groupLabel
    # appearing in the title — not necessarily both. DBU's own titling is
    # inconsistent: Herre-DS's base Grundspil groups are titled "<name>,
    # Pulje N" with NO "Grundspil" suffix (unlike Superliga/Betinia
    # LIGA/CampoBet/A-Liga/B-Liga, which all say "- Grundspil" explicitly),
    # while a one-off pulje like the Superliga "Europa Playoff" carries a
    # groupLabel that IS the distinguishing text instead of any of the fixed
    # phase vocabulary. Requiring "phase label present" unconditionally
    # produced false MISMATCHes against real, correct titles during T4 —
    # see docs/specs/dk-results-scraper/discovery-notes.md.
    phase_label = PHASE_LABEL_DA.get(pulje.phase)
    phase_label_present = phase_label is not None and phase_label.lower() in title.lower()
    group_label_present = bool(pulje.groupLabel) and pulje.groupLabel.lower() in title.lower()

    if phase_label is not None and not (phase_label_present or group_label_present):
        return (
            f"title {title!r} contains neither the expected phase label "
            f"{phase_label!r} nor the declared group label {pulje.groupLabel!r}"
        )

    if pulje.groupLabel and not group_label_present and not phase_label_present:
        return f"title {title!r} does not contain expected group label {pulje.groupLabel!r}"

    return None
