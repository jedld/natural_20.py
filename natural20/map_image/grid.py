"""Parse map YAML layers into a render-friendly grid."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from natural20.yaml_loader import load_yaml


@dataclass
class MapGrid:
    name: str = "Map"
    description: str = ""
    width: int = 0
    height: int = 0
    base: list[list[str | None]] = field(default_factory=list)
    base_1: list[list[str | None]] = field(default_factory=list)
    base_2: list[list[str | None]] = field(default_factory=list)
    meta: list[list[str | None]] = field(default_factory=list)
    legend: dict[str, Any] = field(default_factory=dict)
    entities: list[dict[str, Any]] = field(default_factory=list)
    background_image: str | None = None
    image_offset_px: list[int] = field(default_factory=lambda: [0, 0])
    render_hints: dict[str, Any] = field(default_factory=dict)

    def cell(self, layer: str, x: int, y: int) -> str | None:
        grid = {
            "base": self.base,
            "base_1": self.base_1,
            "base_2": self.base_2,
            "meta": self.meta,
        }.get(layer)
        if not grid or x < 0 or y < 0 or x >= self.width or y >= self.height:
            return None
        return grid[x][y]


def _blank_grid(width: int, height: int, fill: str | None = None) -> list[list[str | None]]:
    return [[fill for _ in range(height)] for _ in range(width)]


def _fill_layer(rows: list[str], width: int, height: int, *, skip: set[str] | None = None) -> list[list[str | None]]:
    skip = skip or set()
    grid = _blank_grid(width, height)
    for y, row in enumerate(rows):
        if y >= height:
            break
        for x, char in enumerate(row):
            if x >= width:
                break
            if char in skip:
                continue
            grid[x][y] = char
    return grid


def map_grid_from_properties(properties: dict[str, Any]) -> MapGrid:
    map_block = properties.get("map", {}) or {}
    base_rows = map_block.get("base") or ["."]
    manual_size = map_block.get("size")
    if manual_size:
        width, height = int(manual_size[0]), int(manual_size[1])
    else:
        height = len(base_rows)
        width = len(base_rows[0]) if base_rows else 0

    render_hints = properties.get("render") or map_block.get("render") or {}

    return MapGrid(
        name=properties.get("name", "Map"),
        description=properties.get("description", "") or "",
        width=width,
        height=height,
        base=_fill_layer(base_rows, width, height, skip={"_"}),
        base_1=_fill_layer(map_block.get("base_1") or [], width, height, skip={"."}),
        base_2=_fill_layer(map_block.get("base_2") or [], width, height, skip={"."}),
        meta=_fill_layer(map_block.get("meta") or [], width, height, skip={"."}),
        legend=properties.get("legend") or {},
        entities=list(map_block.get("entities") or []),
        background_image=properties.get("background_image"),
        image_offset_px=list(properties.get("image_offset_px") or [0, 0]),
        render_hints=render_hints if isinstance(render_hints, dict) else {},
    )


def load_map_grid(path: str | Path, *, campaign_root: str | Path | None = None) -> MapGrid:
    properties = load_yaml(path, campaign_root=campaign_root)
    if not isinstance(properties, dict):
        raise ValueError(f"Map YAML must be a mapping: {path}")
    return map_grid_from_properties(properties)


def load_map_grid_from_campaign(campaign_root: str | Path, map_name: str) -> MapGrid:
    campaign = Path(campaign_root).resolve()
    map_path = map_name
    if not map_path.endswith(".yml"):
        map_path = f"{map_path}.yml"
    candidates = [
        campaign / map_path,
        campaign / "maps" / Path(map_path).name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return load_map_grid(candidate, campaign_root=campaign)
    raise FileNotFoundError(f"Map not found for {map_name!r} under {campaign}")
