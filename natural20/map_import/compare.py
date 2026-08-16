"""Compare an imported map YAML against a hand-authored gold map.

Occupancy uses legend types so directional stone walls and campaign door
glyphs count, not only `#` / `-` / `|`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


def cell_kind(token: str | None, legend: dict[str, Any] | None) -> str:
    """Classify a base-layer glyph as floor, void, wall, door, or other."""
    if token in {None, ".", ""}:
        return "floor"
    if token == "_":
        return "void"
    if token in {"-", "|"}:
        return "door"
    entry = (legend or {}).get(token) or {}
    typ = str(entry.get("type") or "").lower()
    if "door" in typ:
        return "door"
    if token == "#" or "wall" in typ:
        return "wall"
    return "other"


@dataclass
class Occupancy:
    walls: set[tuple[int, int]]
    doors: set[tuple[int, int]]
    blocked: set[tuple[int, int]]
    floors: set[tuple[int, int]]
    width: int
    height: int


def occupancy_sets(properties: dict[str, Any]) -> Occupancy:
    rows = list((properties.get("map") or {}).get("base") or [])
    legend = properties.get("legend") or {}
    height = len(rows)
    width = max((len(row) for row in rows), default=0)
    walls: set[tuple[int, int]] = set()
    doors: set[tuple[int, int]] = set()
    blocked: set[tuple[int, int]] = set()
    floors: set[tuple[int, int]] = set()
    for y, row in enumerate(rows):
        for x, token in enumerate(row):
            kind = cell_kind(token, legend)
            pos = (x, y)
            if kind == "wall":
                walls.add(pos)
                blocked.add(pos)
            elif kind == "door":
                doors.add(pos)
                blocked.add(pos)
            elif kind == "floor":
                floors.add(pos)
    return Occupancy(
        walls=walls,
        doors=doors,
        blocked=blocked,
        floors=floors,
        width=width,
        height=height,
    )


def _iou(a: set[tuple[int, int]], b: set[tuple[int, int]]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def _recall(gold: set[tuple[int, int]], pred: set[tuple[int, int]]) -> float:
    if not gold:
        return 1.0
    return len(gold & pred) / len(gold)


def compare_map_properties(gold: dict[str, Any], generated: dict[str, Any]) -> dict[str, Any]:
    g = occupancy_sets(gold)
    p = occupancy_sets(generated)
    return {
        "gold_size": [g.width, g.height],
        "generated_size": [p.width, p.height],
        "wall_iou": round(_iou(g.walls, p.walls), 4),
        "door_recall": round(_recall(g.doors, p.doors), 4),
        "door_precision": round(_recall(p.doors, g.doors), 4),
        "occupancy_iou": round(_iou(g.blocked, p.blocked), 4),
        "gold_walls": len(g.walls),
        "generated_walls": len(p.walls),
        "gold_doors": len(g.doors),
        "generated_doors": len(p.doors),
        "wall_false_negatives": sorted(g.walls - p.walls)[:40],
        "wall_false_positives": sorted(p.walls - g.walls)[:40],
        "door_false_negatives": sorted(g.doors - p.doors)[:40],
    }


def load_map_yaml(path: str | Path) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Map YAML is not an object: {path}")
    return data


def compare_map_files(gold_path: str | Path, generated_path: str | Path) -> dict[str, Any]:
    report = compare_map_properties(load_map_yaml(gold_path), load_map_yaml(generated_path))
    report["gold"] = str(gold_path)
    report["generated"] = str(generated_path)
    return report
