"""tests/golden/matches.sample.jsonl is the T8 parallel-workstream contract
artefact: ~50-80 SYNTHETIC matches (never real scraped data — see Risk R-6)
spanning every bracket, several phases, penalty shootouts, and not-played/
walkover statuses. This test keeps it schema-valid and representative as
the schema evolves, and is what Phase C (T9-T13) can build/test against
without a scraper or a warm cache.
"""

from __future__ import annotations

import json
from pathlib import Path

from dkfr.normalize.records import MatchRecord
from dkfr.vocab import Bracket, MatchStatus

GOLDEN_PATH = Path(__file__).parent / "golden" / "matches.sample.jsonl"


def _load() -> list[MatchRecord]:
    records = []
    for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines():
        records.append(MatchRecord.model_validate(json.loads(line)))
    return records


def test_golden_sample_is_schema_valid():
    records = _load()
    assert 50 <= len(records) <= 200


def test_golden_sample_spans_every_bracket():
    records = _load()
    brackets = {r.bracket for r in records}
    assert brackets == set(Bracket)


def test_golden_sample_has_multiple_phases():
    records = _load()
    phases = {r.phase.value for r in records}
    expected = {"GRUNDSPIL", "MESTERSKABSSPIL", "OPRYKNINGSSPIL", "KVALIFIKATIONSSPIL", "SINGLE"}
    assert expected <= phases


def test_golden_sample_has_penalty_shootouts():
    records = _load()
    assert any(r.hasPenalties for r in records)
    for r in records:
        if r.hasPenalties:
            assert r.penaltyHomeGoals is not None
            assert r.penaltyAwayGoals is not None
            assert r.penaltyHomeGoals != r.penaltyAwayGoals  # no drawn shootouts


def test_golden_sample_has_not_played_and_walkover_statuses():
    records = _load()
    statuses = {r.status for r in records}
    assert MatchStatus.NOT_PLAYED in statuses
    assert MatchStatus.WALKOVER in statuses
    for r in records:
        if r.status in (MatchStatus.NOT_PLAYED, MatchStatus.WALKOVER):
            assert r.homeGoals is None
            assert r.awayGoals is None


def test_golden_sample_match_keys_are_unique():
    records = _load()
    keys = [r.matchKey for r in records]
    assert len(keys) == len(set(keys))


def test_golden_sample_home_and_away_teams_always_distinct():
    records = _load()
    for r in records:
        assert r.homeTeamId != r.awayTeamId
