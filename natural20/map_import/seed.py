"""Seed a classification grid from an occupancy / map YAML base layer.

Used so a cheap first pass (heuristic or color occupancy) can be given to the
per-tile VLM as a prior instead of throwing it away.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from natural20.map_import.ink import EdgeBits
from natural20.map_import.model import ClassificationGrid, TileRecord
from natural20.map_import.taxonomy import wall_token_edges


def seed_grid_from_base(grid: ClassificationGrid, rows: list[str], *, source: str = "occupancy") -> int:
    """Copy ``#._-|`` / directional glyphs onto the grid. Returns tiles written."""
    height = min(grid.height, len(rows))
    written = 0
    for y in range(height):
        row = rows[y]
        width = min(grid.width, len(row))
        for x in range(width):
            record = _record_from_token(x, y, row[x], source=source)
            if record is None:
                continue
            existing = grid.tiles[x][y]
            record.features = existing.features
            grid.set(record)
            written += 1
    return written


def seed_grid_from_map_yaml(grid: ClassificationGrid, path: str | Path, *, source: str = "occupancy") -> int:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    rows = ((data or {}).get("map") or {}).get("base") or []
    if not isinstance(rows, list):
        return 0
    return seed_grid_from_base(grid, [str(row) for row in rows], source=source)


def seed_map_properties(path: str | Path) -> dict[str, Any] | None:
    """Load a campaign map YAML for merging entities/legend after re-export."""
    dest = Path(path)
    if not dest.is_file():
        return None
    data = yaml.safe_load(dest.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def _record_from_token(x: int, y: int, token: str, *, source: str) -> TileRecord | None:
    if not token:
        return None
    edges = EdgeBits()
    tile_class = "floor"
    subtype = "none"
    orientation = "none"
    bits = wall_token_edges(token)
    if token == "#":
        tile_class = "wall"
        edges.solid = True
    elif token == "_":
        tile_class = "void"
    elif token == ".":
        tile_class = "floor"
    elif token == "-":
        tile_class = "door"
        subtype = "wooden_door"
        orientation = "horizontal"
        edges.door_N = True
        edges.door_S = True
    elif token == "|":
        tile_class = "door"
        subtype = "wooden_door"
        orientation = "vertical"
        edges.door_E = True
        edges.door_W = True
    elif bits is not None:
        tile_class = "wall"
        edges.N, edges.E, edges.S, edges.W = (bool(b) for b in bits)
    else:
        return None
    return TileRecord(
        x=x,
        y=y,
        tile_class=tile_class,
        subtype=subtype,
        orientation=orientation,
        confidence=0.72,
        description=f"{source} prior {token!r}",
        source=source,
        edges=edges,
        flags=[source],
    )
