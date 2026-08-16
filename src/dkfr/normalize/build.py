"""Assemble a NormalizedDataset from parsed pulje results + team/club
resolution. This is the heart of stage [2] — everything downstream
(writer.py, and eventually the loader) reads only what this module
produces, never the raw HTML or BeautifulSoup structures directly.
"""

from __future__ import annotations

from dkfr import __version__
from dkfr.manifest import Manifest
from dkfr.normalize.names import normalize_display_name, slugify
from dkfr.normalize.records import (
    ClubRecord,
    CompetitionRecord,
    MatchRecord,
    NormalizedDataset,
    PuljeRecord,
    StandingRecord,
    TeamRecord,
    VenueRecord,
)
from dkfr.normalize.resolver import TeamResolver
from dkfr.parse.fixtures import extract_team_ids
from dkfr.parse.run import PuljeParseResult
from dkfr.parse.values import to_instant
from dkfr.vocab import AgeBracket, Bracket, Gender, derive_bracket

SEASON = "2025/26"

_GENDER_FOR_BRACKET: dict[Bracket, Gender] = {
    Bracket.MEN_SENIOR: Gender.MEN,
    Bracket.MEN_U19: Gender.MEN,
    Bracket.MEN_U17: Gender.MEN,
    Bracket.WOMEN_SENIOR: Gender.WOMEN,
    Bracket.WOMEN_U19: Gender.WOMEN,
    Bracket.WOMEN_U16: Gender.WOMEN,
}

_AGE_BRACKET_FOR_BRACKET: dict[Bracket, AgeBracket] = {
    Bracket.MEN_SENIOR: AgeBracket.SENIOR,
    Bracket.WOMEN_SENIOR: AgeBracket.SENIOR,
    Bracket.MEN_U19: AgeBracket.U19,
    Bracket.WOMEN_U19: AgeBracket.U19,
    Bracket.MEN_U17: AgeBracket.U17,
    Bracket.WOMEN_U16: AgeBracket.U16,
}


def _venue_key(name: str | None) -> str | None:
    if not name:
        return None
    return slugify(name)


def _fallback_match_key(pulje_id: int, iso_date: str, home_id: str, away_id: str) -> str:
    return f"{pulje_id}:{iso_date}:{home_id}:{away_id}"


def build_dataset(
    manifest: Manifest, results: list[PuljeParseResult], resolver: TeamResolver
) -> NormalizedDataset:
    matches: list[MatchRecord] = []
    standings: list[StandingRecord] = []
    puljer: list[PuljeRecord] = []
    competitions: dict[str, CompetitionRecord] = {}
    teams: dict[str, TeamRecord] = {}
    clubs: dict[str, ClubRecord] = {}
    venues: dict[str, VenueRecord] = {}

    for comp_id, comp in manifest.competitions.items():
        competitions[comp_id] = CompetitionRecord(
            competitionId=comp_id,
            name=comp.name,
            bracket=comp.bracket,
            gender=comp.gender,
            ageBracket=comp.ageBracket,
            tier=comp.tier,
            administrator=comp.administrator,
        )

    for result in results:
        pulje = result.pulje
        competition = manifest.competition_for(pulje)
        bracket = derive_bracket(competition.gender, competition.ageBracket)

        puljer.append(
            PuljeRecord(
                puljeId=pulje.puljeId,
                puljeName=None,  # title text isn't retained by the parsers; see README limitations
                competitionId=pulje.competitionId,
                competitionName=competition.name,
                phase=pulje.phase,
                tier=competition.tier,
                bracket=bracket,
                gender=competition.gender,
                ageBracket=competition.ageBracket,
                season=SEASON,
                groupLabel=pulje.groupLabel,
                administrator=competition.administrator,
                pointsCarryOver=pulje.pointsCarryOver,
                teamCount=len(result.teams),
                matchCount=len(result.matches),
                sourceUrl=result.fixturesMeta.sourceUrl,
                fetchedAt=result.fixturesMeta.fetchedAt,
            )
        )

        # Register every roster team even if it never appears in a parsed
        # match row (e.g. a team that withdrew before playing) — holdoversigt
        # is the authoritative roster.
        for entry in result.teams:
            resolved = resolver.resolve_team(
                raw_name=entry.displayName,
                dbu_team_id=entry.dbuTeamId,
                bracket=bracket,
                context=result.teamsMeta.sourceUrl,
            )
            _register_team(teams, clubs, resolved, entry.displayName)

        for match in result.matches:
            home_id_raw, away_id_raw = extract_team_ids(match)
            home = resolver.resolve_team(
                raw_name=match.homeTeamName,
                dbu_team_id=home_id_raw,
                bracket=bracket,
                context=result.fixturesMeta.sourceUrl,
            )
            away = resolver.resolve_team(
                raw_name=match.awayTeamName,
                dbu_team_id=away_id_raw,
                bracket=bracket,
                context=result.fixturesMeta.sourceUrl,
            )
            _register_team(teams, clubs, home, match.homeTeamName)
            _register_team(teams, clubs, away, match.awayTeamName)

            venue_key = _venue_key(match.venueName)
            if venue_key and venue_key not in venues:
                venues[venue_key] = VenueRecord(venueKey=venue_key, name=match.venueName)

            if match.matchNumber:
                match_key = f"{pulje.puljeId}:{match.matchNumber}"
            else:
                match_key = _fallback_match_key(
                    pulje.puljeId,
                    match.date.isoformat() if match.date else "unknown-date",
                    home.teamId,
                    away.teamId,
                )

            total_goals = (
                match.homeGoals + match.awayGoals
                if match.homeGoals is not None and match.awayGoals is not None
                else None
            )
            goal_margin = (
                abs(match.homeGoals - match.awayGoals)
                if match.homeGoals is not None and match.awayGoals is not None
                else None
            )

            matches.append(
                MatchRecord(
                    matchKey=match_key,
                    matchNumber=match.matchNumber,
                    puljeId=pulje.puljeId,
                    competitionId=pulje.competitionId,
                    competitionName=competition.name,
                    phase=pulje.phase,
                    tier=competition.tier,
                    bracket=bracket,
                    gender=competition.gender,
                    ageBracket=competition.ageBracket,
                    season=SEASON,
                    date=match.date,
                    kickoffTimeLocal=match.kickoffTime,
                    kickoffAt=_to_instant(match),
                    homeTeamId=home.teamId,
                    homeTeamName=normalize_display_name(match.homeTeamName),
                    awayTeamId=away.teamId,
                    awayTeamName=normalize_display_name(match.awayTeamName),
                    homeGoals=match.homeGoals,
                    awayGoals=match.awayGoals,
                    penaltyHomeGoals=match.penaltyHomeGoals,
                    penaltyAwayGoals=match.penaltyAwayGoals,
                    hasPenalties=match.penaltyHomeGoals is not None,
                    totalGoals=total_goals,
                    goalMargin=goal_margin,
                    status=match.status,
                    venueName=match.venueName,
                    venueKey=venue_key,
                    sourceUrl=result.fixturesMeta.sourceUrl,
                    fetchedAt=result.fixturesMeta.fetchedAt or "",
                    scraperVersion=__version__,
                )
            )

        for row in result.standings:
            if row.teamId is None:
                continue
            team_id = f"dbu:{row.teamId}"
            standings.append(
                StandingRecord(
                    puljeId=pulje.puljeId,
                    teamId=team_id,
                    teamName=normalize_display_name(row.teamName),
                    rank=row.rank,
                    played=row.played,
                    won=row.homeWon + row.awayWon,
                    drawn=row.homeDrawn + row.awayDrawn,
                    lost=row.homeLost + row.awayLost,
                    goalsFor=row.totalGoalsFor,
                    goalsAgainst=row.totalGoalsAgainst,
                    goalDifference=row.totalGoalsFor - row.totalGoalsAgainst,
                    points=row.points,
                    sourceUrl=result.standingsMeta.sourceUrl,
                    fetchedAt=result.standingsMeta.fetchedAt or "",
                )
            )

    return NormalizedDataset(
        matches=matches,
        standings=standings,
        puljer=puljer,
        competitions=list(competitions.values()),
        teams=list(teams.values()),
        clubs=list(clubs.values()),
        venues=list(venues.values()),
    )


def _register_team(teams: dict, clubs: dict, resolved, raw_name: str) -> None:
    if resolved.teamId not in teams:
        teams[resolved.teamId] = TeamRecord(
            teamId=resolved.teamId,
            name=resolved.canonicalName,
            bracket=resolved.bracket,
            gender=_GENDER_FOR_BRACKET[resolved.bracket],
            ageBracket=_AGE_BRACKET_FOR_BRACKET[resolved.bracket],
            squadIndex=resolved.squadIndex,
            dbuTeamId=resolved.dbuTeamId,
            clubId=resolved.clubId,
            sourceNames=[normalize_display_name(raw_name)],
        )
    else:
        existing = teams[resolved.teamId]
        norm = normalize_display_name(raw_name)
        if norm not in existing.sourceNames:
            existing.sourceNames.append(norm)

    if resolved.clubId not in clubs:
        clubs[resolved.clubId] = ClubRecord(clubId=resolved.clubId, name=resolved.canonicalName)


def _to_instant(match):
    if match.date is None:
        return None
    return to_instant(match.date, match.kickoffTime)
