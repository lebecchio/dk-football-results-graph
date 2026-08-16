"""Deterministic writers for data/normalized/*. Sorted keys, stable record
ordering, ensure_ascii=False, LF line endings, trailing newline — this is
what makes AC7 (byte-identical re-parse of a warm cache) achievable.
"""

from __future__ import annotations

import json
from pathlib import Path

from dkfr.normalize.records import NormalizedDataset

# Pydantic's model_dump(mode="json") already produces JSON-safe primitives
# (dates/times as ISO strings, enums as their values).


def _dump(model) -> dict:
    return model.model_dump(mode="json")


def write_normalized_dataset(dataset: NormalizedDataset, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    matches_sorted = sorted(dataset.matches, key=lambda m: (m.puljeId, m.date, m.matchKey))
    matches_path = out_dir / "matches.jsonl"
    with matches_path.open("w", encoding="utf-8", newline="\n") as f:
        for m in matches_sorted:
            f.write(json.dumps(_dump(m), sort_keys=True, ensure_ascii=False) + "\n")
    paths["matches"] = matches_path

    standings_sorted = sorted(dataset.standings, key=lambda s: (s.puljeId, s.rank))
    standings_path = out_dir / "standings.jsonl"
    with standings_path.open("w", encoding="utf-8", newline="\n") as f:
        for s in standings_sorted:
            f.write(json.dumps(_dump(s), sort_keys=True, ensure_ascii=False) + "\n")
    paths["standings"] = standings_path

    def write_json_array(name: str, items: list, key) -> None:
        items_sorted = sorted(items, key=key)
        path = out_dir / f"{name}.json"
        path.write_text(
            json.dumps(
                [_dump(i) for i in items_sorted], indent=2, sort_keys=True, ensure_ascii=False
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        paths[name] = path

    write_json_array("puljer", dataset.puljer, key=lambda p: p.puljeId)
    write_json_array("competitions", dataset.competitions, key=lambda c: c.competitionId)
    write_json_array("teams", dataset.teams, key=lambda t: t.teamId)
    write_json_array("clubs", dataset.clubs, key=lambda c: c.clubId)
    write_json_array("venues", dataset.venues, key=lambda v: v.venueKey)

    return paths
