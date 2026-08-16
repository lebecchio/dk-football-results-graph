"""TeamResolver / ClubResolver tests — design Decision 3 / spec AC10.

Uses synthetic inputs for the pure-logic cases, plus one test against the
real cached T6 fetch (data/cache/, gitignored) to confirm the resolver
behaves correctly on the actual dataset — marked so it skips cleanly if the
cache isn't present (e.g. a fresh checkout with no prior fetch).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dkfr.normalize.names import slugify, split_squad_ordinal
from dkfr.normalize.resolver import ClubAlias, TeamResolver, load_club_overrides
from dkfr.vocab import Bracket


def test_same_team_across_grundspil_and_mesterskabsspil_resolves_to_one_id():
    resolver = TeamResolver()
    a = resolver.resolve_team(
        raw_name="FC Midtjylland",
        dbu_team_id="6206",
        bracket=Bracket.MEN_SENIOR,
        context="grundspil",
    )
    b = resolver.resolve_team(
        raw_name="FC Midtjylland", dbu_team_id="6206", bracket=Bracket.MEN_SENIOR, context="mester"
    )
    assert a.teamId == b.teamId == "dbu:6206"


def test_same_short_name_in_different_brackets_resolves_to_two_ids():
    resolver = TeamResolver()
    senior = resolver.resolve_team(
        raw_name="AGF", dbu_team_id="8838", bracket=Bracket.MEN_SENIOR, context="senior"
    )
    u19 = resolver.resolve_team(
        raw_name="AGF", dbu_team_id="8825", bracket=Bracket.MEN_U19, context="u19"
    )
    assert senior.teamId != u19.teamId
    assert senior.teamId == "dbu:8838"
    assert u19.teamId == "dbu:8825"
    # Same club regardless of bracket (U7/AC18 depends on this).
    assert senior.clubId == u19.clubId == "agf"


def test_missing_dbu_team_id_falls_back_to_name_key_and_reports_unresolved():
    resolver = TeamResolver()
    result = resolver.resolve_team(
        raw_name="Some New Club", dbu_team_id=None, bracket=Bracket.MEN_SENIOR, context="test-url"
    )
    assert result.teamId == "name:some-new-club|MEN_SENIOR"
    assert result.resolvedViaFallback is True
    assert len(resolver.unresolved) == 1
    assert resolver.unresolved[0].rawName == "Some New Club"


def test_squad_ordinal_splitting():
    assert split_squad_ordinal("AaB 2") == ("AaB", 2)
    assert split_squad_ordinal("B 93 (2)") == ("B 93", 2)
    assert split_squad_ordinal("Brøndby IF II") == ("Brøndby IF", 2)
    assert split_squad_ordinal("FC København") == ("FC København", None)
    # "B 93" -- trailing number out of the 2-9 squad-ordinal range, not split
    assert split_squad_ordinal("B 93") == ("B 93", None)


def test_club_override_applied():
    overrides = {"f.c. københavn": ClubAlias(clubId="fc-koebenhavn", displayName="FC København")}
    resolver = TeamResolver(club_overrides=overrides)
    result = resolver.resolve_team(
        raw_name="F.C. København", dbu_team_id="52769", bracket=Bracket.MEN_SENIOR, context="x"
    )
    assert result.clubId == "fc-koebenhavn"


def test_load_club_overrides_from_real_manifest_file():
    overrides = load_club_overrides(Path("manifest/clubs.yaml"))
    assert "f.c. københavn" in overrides
    assert overrides["f.c. københavn"].clubId == "fc-koebenhavn"


def test_default_club_slug_groups_fck_variants_only_with_override():
    # Without the override, the two real FCK spellings found in the T6 fetch
    # produce DIFFERENT slugs — this is exactly why the override exists.
    assert slugify("F.C. København") != slugify("FC København")


@pytest.mark.live_cache
def test_fck_resolves_to_one_club_across_the_real_cached_manifest():
    """Regression test against the real T3/T4/T6 fetch: FC København's teams
    across Superliga (senior), B-Liga (women's senior), and U19/U17 Drenge
    Ligaen must all resolve to the SAME clubId once the override is applied.
    Skips if the cache isn't present."""
    cache_dir = Path("data/cache/pulje")
    if not cache_dir.exists():
        pytest.skip("data/cache not present — run `dkfr fetch --all` first")

    from dkfr.parse.teams import parse_teams

    overrides = load_club_overrides(Path("manifest/clubs.yaml"))
    resolver = TeamResolver(club_overrides=overrides)

    bracket_by_pulje = {
        "473806": Bracket.MEN_SENIOR,  # Superliga Grundspil
        "474287": Bracket.WOMEN_SENIOR,  # B-Liga (women's — separate club entity)
        "473921": Bracket.MEN_U19,
        "473922": Bracket.MEN_U17,
    }
    club_ids = set()
    for pulje_id, bracket in bracket_by_pulje.items():
        f = cache_dir / pulje_id / "holdoversigt.html"
        if not f.exists():
            pytest.skip(f"pulje {pulje_id} not cached")
        entries, _ = parse_teams(f.read_text(encoding="utf-8"), str(f))
        fck = [e for e in entries if "benhavn" in e.displayName.lower()]
        if not fck:
            continue
        result = resolver.resolve_team(
            raw_name=fck[0].displayName,
            dbu_team_id=fck[0].dbuTeamId,
            bracket=bracket,
            context=str(f),
        )
        club_ids.add(result.clubId)

    assert club_ids == {"fc-koebenhavn"}
