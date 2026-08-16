"""Manifest schema/referential-integrity tests, and title-check unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from dkfr.config import get_settings
from dkfr.manifest import CompetitionEntry, Manifest, PuljeEntry, check_pulje_title, load_manifest
from dkfr.vocab import Administrator, AgeBracket, Bracket, Gender, Phase


def test_real_manifest_loads_and_validates():
    settings = get_settings()
    manifest = load_manifest(settings.puljer_manifest_path)
    assert len(manifest.competitions) >= 10
    assert len(manifest.puljer) >= 30
    # every puljeId is unique (checked by the model validator, but assert too)
    ids = [p.puljeId for p in manifest.puljer]
    assert len(ids) == len(set(ids))


def test_bracket_gender_age_mismatch_rejected():
    with pytest.raises(ValidationError):
        CompetitionEntry(
            name="Bad",
            bracket=Bracket.MEN_SENIOR,
            gender=Gender.WOMEN,
            ageBracket=AgeBracket.SENIOR,
            tier=1,
            administrator=Administrator.DBU,
        )


def test_unknown_competition_id_rejected():
    with pytest.raises(ValidationError):
        Manifest(
            competitions={
                "x": CompetitionEntry(
                    name="X",
                    bracket=Bracket.MEN_SENIOR,
                    gender=Gender.MEN,
                    ageBracket=AgeBracket.SENIOR,
                    tier=1,
                    administrator=Administrator.DBU,
                )
            },
            puljer=[
                PuljeEntry(puljeId=1, competitionId="does-not-exist", phase=Phase.SINGLE),
            ],
        )


def test_duplicate_pulje_id_rejected():
    comp = CompetitionEntry(
        name="X",
        bracket=Bracket.MEN_SENIOR,
        gender=Gender.MEN,
        ageBracket=AgeBracket.SENIOR,
        tier=1,
        administrator=Administrator.DBU,
    )
    with pytest.raises(ValidationError):
        Manifest(
            competitions={"x": comp},
            puljer=[
                PuljeEntry(puljeId=1, competitionId="x", phase=Phase.SINGLE),
                PuljeEntry(puljeId=1, competitionId="x", phase=Phase.SINGLE),
            ],
        )


def test_check_pulje_title_ok():
    comp = CompetitionEntry(
        name="3F Superliga",
        bracket=Bracket.MEN_SENIOR,
        gender=Gender.MEN,
        ageBracket=AgeBracket.SENIOR,
        tier=1,
        administrator=Administrator.DIVISIONSFORENINGEN,
    )
    pulje = PuljeEntry(puljeId=473806, competitionId="3f-superliga", phase=Phase.GRUNDSPIL)
    assert check_pulje_title("3F Superliga - Grundspil 2025/26 (2026)", comp, pulje) is None


def test_check_pulje_title_wrong_phase():
    comp = CompetitionEntry(
        name="3F Superliga",
        bracket=Bracket.MEN_SENIOR,
        gender=Gender.MEN,
        ageBracket=AgeBracket.SENIOR,
        tier=1,
        administrator=Administrator.DIVISIONSFORENINGEN,
    )
    pulje = PuljeEntry(puljeId=498492, competitionId="3f-superliga", phase=Phase.GRUNDSPIL)
    reason = check_pulje_title("3F Superliga - Mesterskabsspil 2025/26 (2026)", comp, pulje)
    assert reason is not None
    assert "Grundspil" in reason


def test_check_pulje_title_distinguishes_2nd_and_3rd_division():
    comp2 = CompetitionEntry(
        name="CampoBet 2. Division",
        bracket=Bracket.MEN_SENIOR,
        gender=Gender.MEN,
        ageBracket=AgeBracket.SENIOR,
        tier=3,
        administrator=Administrator.DBU,
    )
    pulje = PuljeEntry(puljeId=1, competitionId="x", phase=Phase.GRUNDSPIL)
    # A 3. Division title must NOT satisfy a 2. Division manifest entry.
    reason = check_pulje_title("CampoBet 3. Division - Grundspil 2025/26 (2026)", comp2, pulje)
    assert reason is not None


def test_check_pulje_title_wrong_season():
    comp = CompetitionEntry(
        name="3F Superliga",
        bracket=Bracket.MEN_SENIOR,
        gender=Gender.MEN,
        ageBracket=AgeBracket.SENIOR,
        tier=1,
        administrator=Administrator.DIVISIONSFORENINGEN,
    )
    pulje = PuljeEntry(puljeId=1, competitionId="x", phase=Phase.GRUNDSPIL)
    reason = check_pulje_title("3F Superliga - Grundspil 2024/25 (2025)", comp, pulje)
    assert reason is not None
    assert "season code" in reason


def test_manifest_yaml_path_exists():
    settings = get_settings()
    assert Path(settings.puljer_manifest_path).exists()
