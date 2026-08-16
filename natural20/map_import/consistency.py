"""Neighbor-aware cleanup of tile classifications.

Uses the running identification grid so isolated misreads (a wall in the
middle of a room, a door with no walls, furniture on a wall) can be corrected
before YAML export. Optional LLM review sees the ASCII map plus the log of
low-confidence tiles.
"""

from __future__ import annotations

import json
from typing import Any

from natural20.map_import.ink import apply_edges_to_record, reconcile_adjacent_edges, rehome_outline_edges
from natural20.map_import.json_util import parse_json_object
from natural20.map_import.model import ClassificationGrid, TileRecord
from natural20.map_import.taxonomy import normalize_class, normalize_subtype
from natural20.map_import.vlm import HeuristicClient, VlmClient

CONSISTENCY_SYSTEM = """You review a Natural20 battlemap transcribed tile-by-tile.
You receive an ASCII map and a list of uncertain or inconsistent tiles.
Return JSON only:
{
  "fixes": [
    {"x": 0, "y": 0, "class": "floor", "subtype": "none", "orientation": "none", "reason": "short"}
  ],
  "notes": ["optional observations"]
}
Only fix clear errors. Do not invent rooms that are not in the ASCII. Prefer
keeping walls contiguous and doors between two floor tiles with walls on the
other axis.
"""


def apply_consistency_rules(grid: ClassificationGrid) -> list[dict[str, Any]]:
    """Deterministic neighbor rules. Returns a list of applied fixes."""
    fixes: list[dict[str, Any]] = []
    edge_edits = reconcile_adjacent_edges(grid.tiles, grid.width, grid.height)
    if edge_edits:
        fixes.append({"x": -1, "y": -1, "class": "edges", "reason": f"reconcile_adjacent_edges:{edge_edits}"})
    outline_edits = rehome_outline_edges(grid.tiles, grid.width, grid.height)
    if outline_edits:
        fixes.append({"x": -1, "y": -1, "class": "edges", "reason": f"rehome_outline_edges:{outline_edits}"})
    for y in range(grid.height):
        for x in range(grid.width):
            if _keep_occupancy_class(grid.tiles[x][y]):
                continue
            apply_edges_to_record(grid.tiles[x][y])
    # Multiple passes so door orientation can use cleaned walls.
    for _ in range(3):
        changed = 0
        for y in range(grid.height):
            for x in range(grid.width):
                tile = grid.tiles[x][y]
                fix = _rule_for(grid, tile)
                if not fix:
                    continue
                new_class, new_subtype, reason = fix
                if new_class == tile.tile_class and new_subtype == tile.subtype:
                    if tile.tile_class == "door":
                        orientation = _door_orientation(grid, x, y)
                        if orientation != tile.orientation:
                            tile.orientation = orientation
                            tile.flags.append("door_orientation")
                            fixes.append({"x": x, "y": y, "class": "door", "reason": "orientation"})
                    continue
                tile.flags.append(f"rule:{reason}")
                tile.tile_class = new_class
                tile.subtype = new_subtype
                tile.source = "consistency"
                if new_class == "door":
                    tile.orientation = _door_orientation(grid, x, y)
                else:
                    tile.orientation = "none"
                grid.set(tile)
                fixes.append({"x": x, "y": y, "class": new_class, "subtype": new_subtype, "reason": reason})
                changed += 1
        if changed == 0:
            break
    for y in range(grid.height):
        for x in range(grid.width):
            if _keep_occupancy_class(grid.tiles[x][y]):
                continue
            apply_edges_to_record(grid.tiles[x][y])
    return fixes


def llm_consistency_review(
    grid: ClassificationGrid,
    client: VlmClient,
    *,
    threshold: float = 0.55,
) -> list[dict[str, Any]]:
    if isinstance(client, HeuristicClient):
        return []
    uncertain = grid.uncertain(threshold)[:80]
    issues = _detect_issues(grid)[:40]
    if not uncertain and not issues:
        return []
    prompt = [
        "ASCII map (# wall, . floor, _ void, w water, -| door, letters objects):",
        grid.ascii_map(),
        "",
        "Uncertain tiles:",
    ]
    for tile in uncertain:
        prompt.append(
            f"- ({tile.x},{tile.y}) {tile.neighbor_summary()} desc={tile.description!r} flags={tile.flags}"
        )
    prompt.append("Detected issues:")
    for issue in issues:
        prompt.append(f"- {issue}")
    prompt.append("Return JSON fixes only for genuine errors.")
    text = client.complete("\n".join(prompt), system=CONSISTENCY_SYSTEM, max_tokens=2048)
    try:
        data = parse_json_object(text)
    except (ValueError, json.JSONDecodeError, TypeError):
        return []
    applied: list[dict[str, Any]] = []
    for item in data.get("fixes") or []:
        if not isinstance(item, dict):
            continue
        try:
            x, y = int(item["x"]), int(item["y"])
        except (KeyError, TypeError, ValueError):
            continue
        tile = grid.get(x, y)
        if tile is None or _keep_occupancy_class(tile):
            continue
        tile.tile_class = normalize_class(item.get("class") or tile.tile_class)
        tile.subtype = normalize_subtype(item.get("subtype") or tile.subtype)
        if item.get("orientation"):
            tile.orientation = str(item["orientation"])
        tile.flags.append("llm_consistency")
        tile.source = "consistency_llm"
        tile.description = str(item.get("reason") or tile.description)[:400]
        grid.set(tile)
        applied.append({"x": x, "y": y, "class": tile.tile_class, "reason": item.get("reason")})
    return applied


def _rule_for(grid: ClassificationGrid, tile: TileRecord) -> tuple[str, str, str] | None:
    if any(str(flag).startswith("overlay:") for flag in tile.flags):
        return None
    if _keep_occupancy_class(tile):
        return None
    x, y = tile.x, tile.y
    cardinal = [t for t in grid.cardinal(x, y).values() if t]
    wall_n = sum(1 for t in cardinal if t.tile_class == "wall" or t.edges.any_wall())
    floor_n = sum(1 for t in cardinal if t.tile_class in {"floor", "water", "door"})
    # Isolated wall in a floor field — keep cells that actually have ink walls.
    if tile.tile_class == "wall" and wall_n == 0 and floor_n >= 3:
        if tile.edges.any_wall() or tile.edges.any_door():
            return None
        if tile.confidence < 0.8 or tile.subtype in {"other", "table", "statue"}:
            return "object", tile.subtype if tile.subtype not in {"none"} else "other", "isolated_wall"
        return "floor", "none", "isolated_wall"
    # Isolated floor in a wall field.
    if tile.tile_class == "floor" and floor_n == 0 and wall_n >= 3:
        return "wall", "none", "isolated_floor"
    # Door must sit on a wall edge or touch a wall cell.
    if tile.tile_class == "door" and wall_n == 0:
        if tile.edges.any_door() or tile.edges.any_wall():
            return None
        if tile.subtype not in {"none", "wooden_door"}:
            return "object", tile.subtype, "door_without_wall"
        return "floor", "none", "door_without_wall"
    # Object sitting on a wall with no floor neighbor → keep wall.
    if tile.tile_class == "object" and wall_n >= 3 and floor_n == 0:
        return "wall", "none", "object_in_wall"
    # Low-confidence unknown surrounded by walls.
    if tile.tile_class == "unknown":
        if wall_n >= 3:
            return "wall", "none", "unknown_majority_wall"
        return "floor", "none", "unknown_default_floor"
    return None


def _door_orientation(grid: ClassificationGrid, x: int, y: int) -> str:
    tile = grid.get(x, y)
    if tile is not None:
        side = tile.edges.door_side()
        if side in {"E", "W"}:
            return "vertical"
        if side in {"N", "S"}:
            return "horizontal"
    n = grid.get(x, y - 1)
    s = grid.get(x, y + 1)
    e = grid.get(x + 1, y)
    w = grid.get(x - 1, y)
    ns = sum(1 for t in (n, s) if t and (t.tile_class == "wall" or t.edges.any_wall()))
    ew = sum(1 for t in (e, w) if t and (t.tile_class == "wall" or t.edges.any_wall()))
    return "vertical" if ns >= ew else "horizontal"


def _detect_issues(grid: ClassificationGrid) -> list[str]:
    issues: list[str] = []
    for y in range(grid.height):
        for x in range(grid.width):
            tile = grid.tiles[x][y]
            cardinal = [t for t in grid.cardinal(x, y).values() if t]
            wall_n = sum(1 for t in cardinal if t.tile_class == "wall" or t.edges.any_wall())
            if tile.tile_class == "door" and wall_n == 0 and not tile.edges.any_door() and not tile.edges.any_wall():
                issues.append(f"door at ({x},{y}) has no adjacent wall")
            if tile.tile_class == "wall" and wall_n == 0 and not tile.edges.any_wall():
                issues.append(f"isolated wall at ({x},{y})")
            if tile.tile_class == "object" and tile.subtype == "none":
                issues.append(f"object at ({x},{y}) missing subtype")
    return issues


def _keep_occupancy_class(tile: TileRecord) -> bool:
    """Do not let CV ink rewrite a seeded occupancy class into a door soup."""
    flags = {str(f) for f in (tile.flags or [])}
    if flags & {"occupancy", "seed", "vlm_kept_prior"}:
        return True
    return (tile.source or "") in {"occupancy", "seed"}


def flood_floor(grid: ClassificationGrid, start: tuple[int, int] | None = None) -> set[tuple[int, int]]:
    """Walkable tiles (floor, door, water, objects on floor)."""
    def walkable(tile: TileRecord) -> bool:
        return tile.tile_class in {"floor", "door", "water", "object"}

    if start is None:
        start = next(
            ((x, y) for y in range(grid.height) for x in range(grid.width) if walkable(grid.tiles[x][y])),
            None,
        )
    if start is None:
        return set()
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if (nx, ny) in seen:
                continue
            tile = grid.get(nx, ny)
            if tile is None or not walkable(tile):
                continue
            seen.add((nx, ny))
            stack.append((nx, ny))
    return seen
