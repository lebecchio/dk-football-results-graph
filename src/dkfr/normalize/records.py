"""The [2]->[3] contract: pydantic models for the normalized JSON output.

These are what `data/normalized/*.json(l)` actually contain, and what the
loader (T9+) reads — never raw dicts. AC3's field-completeness requirement
is a model-level guarantee here: every required field is non-Optional on
MatchRecord, so a record that doesn't have it fails validation at write
time, not silently at load time.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from datetime import time as time_type

from pydantic import BaseModel

from dkfr.vocab import Administrator, AgeBracket, Bracket, Gender, MatchStatus, Phase


class MatchRecord(BaseModel):
    matchKey: str  # f"{puljeId}:{matchNumber}" or the deterministic fallback
    matchNumber: str | None
    puljeId: int
    competitionId: str
    competitionName: str
    phase: Phase
    tier: int
    bracket: Bracket
    gender: Gender
    ageBracket: AgeBracket
    season: str
    date: date_type
    kickoffTimeLocal: time_type | None
    kickoffAt: datetime | None
    homeTeamId: str
    homeTeamName: str
    awayTeamId: str
    awayTeamName: str
    homeGoals: int | None
    awayGoals: int | None
    penaltyHomeGoals: int | None
    penaltyAwayGoals: int | None
    hasPenalties: bool
    totalGoals: int | None
    goalMargin: int | None
    status: MatchStatus
    venueName: str | None
    venueKey: str | None
    sourceUrl: str
    fetchedAt: str
    scraperVersion: str


class StandingRecord(BaseModel):
    puljeId: int
    teamId: str
    teamName: str
    rank: int
    played: int
    won: int
    drawn: int
    lost: int
    goalsFor: int
    goalsAgainst: int
    goalDifference: int
    points: int
    sourceUrl: str
    fetchedAt: str


class PuljeRecord(BaseModel):
    puljeId: int
    puljeName: str | None
    competitionId: str
    competitionName: str
    phase: Phase
    tier: int
    bracket: Bracket
    gender: Gender
    ageBracket: AgeBracket
    season: str
    groupLabel: str | None
    administrator: Administrator
    pointsCarryOver: bool
    teamCount: int
    matchCount: int
    sourceUrl: str
    fetchedAt: str | None


class CompetitionRecord(BaseModel):
    competitionId: str
    name: str
    bracket: Bracket
    gender: Gender
    ageBracket: AgeBracket
    tier: int
    administrator: Administrator


class TeamRecord(BaseModel):
    teamId: str
    name: str
    bracket: Bracket
    gender: Gender
    ageBracket: AgeBracket
    squadIndex: int | None
    dbuTeamId: str | None
    clubId: str
    sourceNames: list[str]


class ClubRecord(BaseModel):
    clubId: str
    name: str


class VenueRecord(BaseModel):
    venueKey: str
    name: str


class NormalizedDataset(BaseModel):
    matches: list[MatchRecord]
    standings: list[StandingRecord]
    puljer: list[PuljeRecord]
    competitions: list[CompetitionRecord]
    teams: list[TeamRecord]
    clubs: list[ClubRecord]
    venues: list[VenueRecord]
