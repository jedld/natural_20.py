"""LLM verification of every square against the adventure region it sits in."""

from __future__ import annotations

import json
from typing import Any

from natural20.map_import.adventure import KeyedArea, parse_keyed_areas
from natural20.map_import.json_util import parse_json_object
from natural20.map_import.model import ClassificationGrid, TileRecord
from natural20.map_import.overlays import OverlayReport
from natural20.map_import.taxonomy import normalize_class, normalize_subtype
from natural20.map_import.vlm import HeuristicClient, VlmClient

REGION_SYSTEM = """You verify EVERY listed square of a Natural20 battlemap against the
adventure text for THIS map region (keyed area such as E5a. Hall).

Return JSON only:
{
  "fixes": [
    {"x": 0, "y": 0, "class": "wall|floor|void|water|door|object", "subtype": "none", "orientation": "none", "reason": "short"}
  ],
  "notes": ["optional"]
}

Rules:
- The list contains every square in the region. Omit a square if the current class is correct.
- Only fix clear contradictions with the adventure text or an impossible layout (door with no opening, sealed hall that the text says has four doors, furniture described in this room sitting on a wall).
- class=door for a doorway in a wall (orientation horizontal = N/S opening, vertical = E/W opening).
- Do not redraw the whole room. Do not treat printed keys, titles, or compasses as walls.
- Coordinates are 0-based [x, y], origin top-left.
"""

_CHUNK = 90


def verify_adventure_regions(
    grid: ClassificationGrid,
    adventure_text: str,
    client: VlmClient,
    *,
    overlays: OverlayReport | None = None,
    annotations: list[dict[str, Any]] | None = None,
    apply: bool = True,
) -> dict[str, Any]:
    """Ask the LLM to confirm each square, with the matching keyed adventure excerpt."""
    report: dict[str, Any] = {
        "applied": False,
        "tile_fixes": 0,
        "regions": 0,
        "squares_listed": 0,
        "skipped": None,
    }
    if isinstance(client, HeuristicClient):
        report["skipped"] = "heuristic provider cannot region-verify"
        return report
    keyed = parse_keyed_areas(adventure_text)
    groups = _region_groups(grid, keyed, overlays, annotations or [])
    if not groups:
        groups = [_remainder_group(grid, "map", "Entire map", adventure_text[:2500])]
    fixes = 0
    listed = 0
    region_reports: list[dict[str, Any]] = []
    for group in groups:
        listed += len(group["tiles"])
        applied = _verify_group(grid, client, group, apply=apply)
        fixes += applied
        region_reports.append(
            {
                "id": group["id"],
                "label": group["label"],
                "squares": len(group["tiles"]),
                "fixes": applied,
                "proposed": list(group.get("proposed") or []),
            }
        )
    report["applied"] = True
    report["tile_fixes"] = fixes
    report["regions"] = len(groups)
    report["squares_listed"] = listed
    report["region_reports"] = region_reports
    return report


def _verify_group(grid: ClassificationGrid, client: VlmClient, group: dict[str, Any], *, apply: bool = True) -> int:
    tiles: list[TileRecord] = group["tiles"]
    if not tiles:
        return 0
    applied = 0
    for chunk in _chunks(tiles, _CHUNK):
        prompt = _group_prompt(grid, group, chunk)
        raw = client.complete(prompt, system=REGION_SYSTEM, max_tokens=2048)
        try:
            data = parse_json_object(raw)
        except (ValueError, json.JSONDecodeError, TypeError):
            continue
        allowed = {(t.x, t.y) for t in chunk}
        for item in data.get("fixes") or []:
            if not isinstance(item, dict):
                continue
            try:
                x, y = int(item["x"]), int(item["y"])
            except (KeyError, TypeError, ValueError):
                continue
            if (x, y) not in allowed:
                continue
            tile = grid.get(x, y)
            if tile is None or any(str(f).startswith("overlay:") for f in tile.flags):
                continue
            proposed = {
                "x": x,
                "y": y,
                "class": normalize_class(item.get("class") or tile.tile_class),
                "subtype": normalize_subtype(item.get("subtype") or tile.subtype),
                "reason": str(item.get("reason") or "")[:400],
            }
            group.setdefault("proposed", []).append(proposed)
            if apply:
                tile.tile_class = proposed["class"]
                tile.subtype = proposed["subtype"]
                if item.get("orientation"):
                    tile.orientation = str(item["orientation"])
                tile.flags.append("region_verify")
                tile.source = "region_llm"
                tile.description = proposed["reason"] or tile.description
                grid.set(tile)
            applied += 1
    return applied


def _region_groups(
    grid: ClassificationGrid,
    keyed: list[KeyedArea],
    overlays: OverlayReport | None,
    annotations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_letter = {area.letter: area for area in keyed if area.letter}
    claimed: set[tuple[int, int]] = set()
    groups: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for ann in annotations:
        if not isinstance(ann, dict):
            continue
        letter = str(ann.get("map_key") or "").lower()
        if letter and letter in seen_keys:
            continue
        if letter:
            seen_keys.add(letter)
        bounds = ann.get("bounds") or {}
        cells = _cells_in_bounds(grid, bounds)
        if not cells and letter and overlays:
            for mark in overlays.keys():
                if mark.text.lower() == letter and mark.tiles:
                    pos = (int(mark.tiles[0][0]), int(mark.tiles[0][1]))
                    from natural20.map_import.overlays import flood_room

                    cells = flood_room(grid, pos)
                    break
        if not cells:
            continue
        area = by_letter.get(letter)
        excerpt = area.excerpt(900) if area else str(ann.get("description") or "")[:900]
        title = (area.title if area else ann.get("label")) or letter or ann.get("id")
        code = (area.code if area else None) or str(ann.get("id") or letter)
        tiles = [grid.tiles[x][y] for x, y in cells if grid.get(x, y)]
        if len(tiles) > 200:
            cx = sum(t.x for t in tiles) / len(tiles)
            cy = sum(t.y for t in tiles) / len(tiles)
            tiles = sorted(tiles, key=lambda t: abs(t.x - cx) + abs(t.y - cy))[:200]
            cells = [(t.x, t.y) for t in tiles]
        for x, y in cells:
            claimed.add((x, y))
        groups.append(
            {
                "id": code,
                "label": title,
                "excerpt": excerpt,
                "tiles": tiles,
            }
        )
    leftover = [
        grid.tiles[x][y]
        for y in range(grid.height)
        for x in range(grid.width)
        if (x, y) not in claimed and not any(str(f).startswith("overlay:") for f in grid.tiles[x][y].flags)
    ]
    if leftover:
        intro = keyed[0].body[:1200] if keyed else ""
        groups.append(
            {
                "id": "unkeyed",
                "label": "Squares not inside a printed room key",
                "excerpt": intro or "Exterior, frame, or unlabeled floor around the keyed rooms.",
                "tiles": leftover,
            }
        )
    return groups


def _remainder_group(grid: ClassificationGrid, ident: str, label: str, excerpt: str) -> dict[str, Any]:
    tiles = [grid.tiles[x][y] for y in range(grid.height) for x in range(grid.width)]
    return {"id": ident, "label": label, "excerpt": excerpt, "tiles": tiles}


def _group_prompt(grid: ClassificationGrid, group: dict[str, Any], tiles: list[TileRecord]) -> str:
    xs = [t.x for t in tiles]
    ys = [t.y for t in tiles]
    x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
    crop = _ascii_crop(grid, x1, y1, x2, y2)
    lines = [
        f"Region {group['id']}: {group['label']}",
        "Adventure excerpt for this region:",
        group["excerpt"][:2500],
        "",
        f"ASCII crop of this region (x={x1}..{x2}, y={y1}..{y2}):",
        crop,
        "",
        f"Every square in this batch ({len(tiles)}). Confirm each; return fixes only when wrong:",
    ]
    for tile in tiles:
        lines.append(
            f"- ({tile.x},{tile.y}) {tile.tile_class}/{tile.subtype} "
            f"{tile.edges.summary()} src={tile.source}"
        )
    lines.append("Return JSON only.")
    return "\n".join(lines)


def _ascii_crop(grid: ClassificationGrid, x1: int, y1: int, x2: int, y2: int) -> str:
    x1 = max(0, x1 - 1)
    y1 = max(0, y1 - 1)
    x2 = min(grid.width - 1, x2 + 1)
    y2 = min(grid.height - 1, y2 + 1)
    full = grid.ascii_map().splitlines()
    return "\n".join(full[y][x1 : x2 + 1] for y in range(y1, y2 + 1))


def _cells_in_bounds(grid: ClassificationGrid, bounds: dict[str, Any]) -> list[tuple[int, int]]:
    try:
        x1, y1 = int(bounds["x1"]), int(bounds["y1"])
        x2, y2 = int(bounds["x2"]), int(bounds["y2"])
    except (KeyError, TypeError, ValueError):
        return []
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    cells = []
    for y in range(max(0, y1), min(grid.height, y2 + 1)):
        for x in range(max(0, x1), min(grid.width, x2 + 1)):
            cells.append((x, y))
    return cells


def _chunks(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]
