"""Turn a ClassificationGrid into Natural20 map YAML properties."""

from __future__ import annotations

from typing import Any

import yaml

from natural20.map_import.model import ClassificationGrid
from natural20.map_import.taxonomy import HARDCODED_BASE, mapping_for, legend_entry
from natural20.map_import.thin_wall import merge_thin_wall_legend, prepare_occupancy_walls


def grid_to_map_properties(
    grid: ClassificationGrid,
    *,
    name: str = "Imported Map",
    description: str = "",
    illumination: float = 1.0,
    background_image: str | None = None,
    image_offset_px: list[int] | None = None,
    spawn: tuple[int, int] | None = None,
    extra_entities: list[dict[str, Any]] | None = None,
    extra_legend: dict[str, Any] | None = None,
    map_annotations: list[dict[str, Any]] | None = None,
    needs_wiring: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    width, height = grid.width, grid.height
    base = [["." for _ in range(width)] for _ in range(height)]
    base_1 = [["." for _ in range(width)] for _ in range(height)]
    legend: dict[str, Any] = dict(extra_legend or {})
    wiring = list(needs_wiring or [])

    for y in range(height):
        for x in range(width):
            tile = grid.tiles[x][y]
            mapping = mapping_for(
                tile.tile_class,
                tile.subtype,
                orientation=tile.orientation,
                edges=tile.edges,
            )
            base[y][x] = mapping.base_token
            entry = legend_entry(mapping)
            if mapping.object_token:
                base_1[y][x] = mapping.object_token
                if entry and mapping.object_token not in legend:
                    legend[mapping.object_token] = entry
            elif entry and mapping.base_token not in HARDCODED_BASE and mapping.base_token not in legend:
                legend[mapping.base_token] = entry
            if mapping.needs_wiring:
                wiring.append(
                    {
                        "kind": tile.subtype,
                        "pos": [x, y],
                        "note": mapping.notes,
                    }
                )

    base_rows = prepare_occupancy_walls(["".join(row) for row in base])
    base = [list(row) for row in base_rows]
    legend = merge_thin_wall_legend(legend, base_rows)

    spawn_pos = spawn or _default_spawn(grid)
    props: dict[str, Any] = {
        "name": name,
        "description": description or "Imported from a battlemap image.",
        "map": {
            "illumination": illumination,
            "size": [width, height],
            "base": ["".join(row) for row in base],
            "base_1": ["".join(row) for row in base_1],
            "base_2": ["." * width for _ in range(height)],
            "meta": ["." * width for _ in range(height)],
            "entities": list(extra_entities or []),
        },
        "legend": legend,
        "player_spawn_points": [{"position": [spawn_pos[0], spawn_pos[1]], "group": "a"}],
        "_importer": {
            "width": width,
            "height": height,
            "needs_wiring": wiring,
        },
    }
    if background_image:
        props["background_image"] = background_image
    if image_offset_px:
        props["image_offset_px"] = list(image_offset_px)
    if map_annotations:
        props["map_annotations"] = map_annotations
    return props


def _default_spawn(grid: ClassificationGrid) -> tuple[int, int]:
    for y in range(grid.height):
        for x in range(grid.width):
            if grid.tiles[x][y].tile_class in {"floor", "object"}:
                return x, y
    return grid.width // 2, grid.height // 2


def dump_map_yaml(properties: dict[str, Any]) -> str:
    return yaml.safe_dump(properties, sort_keys=False, allow_unicode=True)


def write_map_yaml(path: str, properties: dict[str, Any]) -> None:
    from pathlib import Path

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(dump_map_yaml(properties), encoding="utf-8")
