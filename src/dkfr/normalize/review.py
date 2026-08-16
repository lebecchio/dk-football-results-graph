"""Generate data/reports/unresolved-names.json: unresolved team names (from
TeamResolver's fallback branch) plus club-grouping suspects (fuzzy-similar
base names that default to different clubIds) — surfaced for human review,
never auto-applied (spec AC10/C9).
"""

from __future__ import annotations

import json
from pathlib import Path

from rapidfuzz import fuzz

from dkfr.manifest import load_manifest
from dkfr.normalize.names import slugify, split_squad_ordinal
from dkfr.normalize.resolver import TeamResolver, load_club_overrides
from dkfr.parse.fixtures import extract_team_ids
from dkfr.parse.run import parse_all
from dkfr.vocab import derive_bracket

CLUB_SUSPECT_THRESHOLD = 80


def build_review_report(*, manifest_path: Path, clubs_path: Path, cache_dir: Path) -> dict:
    manifest = load_manifest(manifest_path)
    club_overrides = load_club_overrides(clubs_path)
    results, _ = parse_all(manifest, cache_dir)

    resolver = TeamResolver(club_overrides=club_overrides)
    all_base_names: dict[str, list[str]] = {}  # base_name -> [pulje_ids seen in]

    for pulje_result in results:
        pulje = pulje_result.pulje
        competition = manifest.competition_for(pulje)
        bracket = derive_bracket(competition.gender, competition.ageBracket)

        for match in pulje_result.matches:
            home_id, away_id = extract_team_ids(match)
            for name, dbu_id in (
                (match.homeTeamName, home_id),
                (match.awayTeamName, away_id),
            ):
                resolver.resolve_team(
                    raw_name=name,
                    dbu_team_id=dbu_id,
                    bracket=bracket,
                    context=str(pulje.puljeId),
                )

        for entry in pulje_result.teams:
            base, _ = split_squad_ordinal(entry.displayName)
            all_base_names.setdefault(base, []).append(str(pulje.puljeId))

    # Club-grouping suspects: distinct base names whose default slug differs
    # but which are fuzzy-similar — flagged, never merged automatically.
    by_slug: dict[str, list[str]] = {}
    overridden_raw_names = set(club_overrides.keys())
    for base in all_base_names:
        if base.lower() in overridden_raw_names:
            continue  # already resolved by a curated override
        by_slug.setdefault(slugify(base), []).append(base)

    distinct = sorted(by_slug.keys())
    suspects = []
    seen_pairs = set()
    for i, s1 in enumerate(distinct):
        for s2 in distinct[i + 1 :]:
            n1, n2 = by_slug[s1][0], by_slug[s2][0]
            score = fuzz.token_sort_ratio(n1, n2)
            if score >= CLUB_SUSPECT_THRESHOLD:
                pair = tuple(sorted((n1, n2)))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                suspects.append(
                    {
                        "nameA": n1,
                        "slugA": s1,
                        "nameB": n2,
                        "slugB": s2,
                        "similarity": round(score, 1),
                        "note": (
                            "Suggestion only — NOT auto-merged. Verify these are the same "
                            "real-world club before adding an override to manifest/clubs.yaml."
                        ),
                    }
                )

    suspects.sort(key=lambda s: -s["similarity"])

    return {
        "unresolvedNames": [
            {
                "rawName": u.rawName,
                "bracket": u.bracket,
                "context": u.context,
                "suggestions": u.suggestions,
            }
            for u in resolver.unresolved
        ],
        "clubGroupingSuspects": suspects,
        "summary": {
            "totalUnresolvedNames": len(resolver.unresolved),
            "totalClubGroupingSuspects": len(suspects),
        },
    }


def write_review_report(
    *, manifest_path: Path, clubs_path: Path, cache_dir: Path, out_path: Path
) -> dict:
    report = build_review_report(
        manifest_path=manifest_path, clubs_path=clubs_path, cache_dir=cache_dir
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    return report
