"""TeamResolver / ClubResolver — design Decision 3.

Q6 (discovery-notes.md) confirmed the DBU numeric team ID is stable across
puljer for the same team, and — critically — that ID is available directly
from every `kampprogramFuld` fixture row's team-cell `href`
(`/resultater/hold/<teamId>_<puljeId>`), not just from a separate
`holdoversigt` fetch. That collapses most of the "resolution pipeline" the
design sketched (normalize -> alias lookup -> roster match -> fuzzy
suggestions): the identity key is available directly, essentially for free,
for every match row in this dataset. The alias/fuzzy machinery below still
exists as the documented fallback for the rare case a row's team link is
missing — never observed in the real 31-pulje manifest fetch, but the
design requires the safety net to exist rather than assume it's never
needed.

Team key: `dbu:<numericTeamId>` (branch 1, confirmed). Club key: default
slug of the squad-ordinal-stripped canonical name, with `manifest/clubs.yaml`
exceptions for cases where the rendered short name differs across brackets.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml
from pydantic import BaseModel
from rapidfuzz import fuzz

from dkfr.normalize.names import normalize_display_name, slugify, split_squad_ordinal
from dkfr.vocab import Bracket

FUZZY_SUGGESTION_THRESHOLD = 85  # rapidfuzz token_sort_ratio, 0-100


class ClubAlias(BaseModel):
    clubId: str
    displayName: str


class ResolvedTeam(BaseModel):
    teamId: str
    canonicalName: str
    squadIndex: int | None
    bracket: Bracket
    dbuTeamId: str | None
    clubId: str
    resolvedViaFallback: bool  # True if dbuTeamId was unavailable (rare/never in practice)


@dataclass
class UnresolvedName:
    rawName: str
    bracket: str
    context: str  # e.g. sourceUrl, for traceability
    suggestions: list[str] = field(default_factory=list)


class TeamResolver:
    """Stateless per call, but caches nothing across brackets — team identity
    is bracket-scoped by construction (Decision 3), so there is no cross-
    bracket cache to accidentally collide on."""

    def __init__(self, club_overrides: dict[str, ClubAlias] | None = None) -> None:
        self._club_overrides = club_overrides or {}
        self._unresolved: list[UnresolvedName] = []
        self._seen_base_names_by_bracket: dict[Bracket, set[str]] = {}

    @property
    def unresolved(self) -> list[UnresolvedName]:
        return self._unresolved

    def resolve_team(
        self,
        *,
        raw_name: str,
        dbu_team_id: str | None,
        bracket: Bracket,
        context: str,
    ) -> ResolvedTeam:
        display_name = normalize_display_name(raw_name)
        base_name, squad_index = split_squad_ordinal(display_name)

        self._seen_base_names_by_bracket.setdefault(bracket, set()).add(base_name)

        if dbu_team_id is not None:
            team_id = f"dbu:{dbu_team_id}"
            resolved_via_fallback = False
        else:
            # Fallback branch — not exercised by the real T6 dataset (every
            # fixture row carries a team href), but required by the design
            # so a future pulje with missing links degrades safely instead
            # of crashing.
            team_id = f"name:{slugify(base_name)}|{bracket.value}"
            resolved_via_fallback = True
            self._unresolved.append(
                UnresolvedName(
                    rawName=raw_name,
                    bracket=bracket.value,
                    context=context,
                    suggestions=self._fuzzy_suggestions(base_name, bracket),
                )
            )

        club_id, club_display = self._resolve_club(base_name)

        return ResolvedTeam(
            teamId=team_id,
            canonicalName=display_name,
            squadIndex=squad_index,
            bracket=bracket,
            dbuTeamId=dbu_team_id,
            clubId=club_id,
            resolvedViaFallback=resolved_via_fallback,
        )

    def _resolve_club(self, base_name: str) -> tuple[str, str]:
        override = self._club_overrides.get(base_name.lower())
        if override is not None:
            return override.clubId, override.displayName
        return slugify(base_name), base_name

    def _fuzzy_suggestions(self, base_name: str, bracket: Bracket) -> list[str]:
        """rapidfuzz *suggestions only* — never auto-resolved (AC10/C9)."""
        candidates = self._seen_base_names_by_bracket.get(bracket, set())
        scored = [
            (fuzz.token_sort_ratio(base_name, c), c) for c in candidates if c != base_name
        ]
        scored.sort(reverse=True)
        return [c for score, c in scored if score >= FUZZY_SUGGESTION_THRESHOLD][:5]


def load_club_overrides(path) -> dict[str, ClubAlias]:  # path: Path
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    overrides: dict[str, ClubAlias] = {}
    for raw_name, entry in (raw.get("overrides") or {}).items():
        overrides[raw_name.lower()] = ClubAlias(
            clubId=entry["clubId"], displayName=entry.get("displayName", raw_name)
        )
    return overrides
