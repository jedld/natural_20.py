"""Export a DungeonGrid to Natural20 map YAML."""

from __future__ import annotations

from typing import Any

import yaml

from natural20.dungeon_gen.knobs import GeneratorKnobs
from natural20.dungeon_gen.model import DOOR_H, DOOR_V, FLOOR, WATER, DungeonGrid
from natural20.dungeon_gen.topology import find_spawn


def grid_to_map_properties(grid: DungeonGrid, knobs: GeneratorKnobs) -> dict[str, Any]:
    base_rows: list[str] = []
    for y in range(grid.height):
        chars = []
        for x in range(grid.width):
            cell = grid.cells[x][y]
            if cell == WATER:
                chars.append("w")
            elif cell in {DOOR_H, DOOR_V}:
                chars.append(cell)
            elif cell == FLOOR:
                chars.append(".")
            else:
                chars.append("#")
        base_rows.append("".join(chars))

    base_1 = [["." for _ in range(grid.width)] for _ in range(grid.height)]
    base_2 = [["." for _ in range(grid.width)] for _ in range(grid.height)]
    meta = [["." for _ in range(grid.width)] for _ in range(grid.height)]

    legend: dict[str, Any] = {
        "w": {"name": "Pool of water", "type": "water"},
    }
    entities: list[dict[str, Any]] = []

    for placement in grid.placements:
        if placement.kind == "spawn":
            continue
        if placement.kind == "door":
            # Already represented by - / | in base
            continue

        token = placement.token
        legend.setdefault(token, placement.legend)

        if placement.entity:
            entities.append(placement.entity)
            continue

        if len(token) == 1:
            layer = {"base_1": base_1, "base_2": base_2, "meta": meta}.get(placement.layer, base_1)
            layer[placement.y][placement.x] = token
        else:
            entity: dict[str, Any] = {
                "token": token,
                "pos": [placement.x, placement.y],
                "name": placement.legend.get("name", token),
                "type": placement.legend.get("type", "interactive_object"),
            }
            if placement.layer in {"base_1", "base_2"}:
                entity["layer"] = "object"
            for key in ("sub_type", "group", "target_map", "target_position", "inventory"):
                if key in placement.legend:
                    entity[key] = placement.legend[key]
            entities.append(entity)

    def rows_from(layer: list[list[str]]) -> list[str]:
        return ["".join(layer[y][x] for x in range(grid.width)) for y in range(grid.height)]

    spawn = find_spawn(grid) or (grid.width // 2, grid.height // 2)
    spawn_points = grid.meta.get("player_spawn_points") or [
        {"position": [spawn[0], spawn[1]], "group": knobs.player_group}
    ]

    props: dict[str, Any] = {
        "name": knobs.name,
        "description": knobs.description
        or f"Procedurally generated {knobs.theme} dungeon (seed={grid.meta.get('seed')}).",
        "render": {
            "palette": _palette_for_theme(knobs.theme),
            "tile_size": 48,
        },
        "map": {
            "illumination": knobs.illumination,
            "size": [grid.width, grid.height],
            "base": base_rows,
            "base_1": rows_from(base_1),
            "base_2": rows_from(base_2),
            "meta": rows_from(meta),
            "entities": entities,
        },
        "legend": legend,
        "player_spawn_points": spawn_points,
        "_generator": {
            "seed": grid.meta.get("seed"),
            "algorithm": knobs.algorithm,
            "theme": knobs.theme,
            "room_roles": {str(r.id): r.role for r in grid.rooms},
            "critical_path": grid.critical_path,
        },
    }

    if knobs.fog:
        props["default_effect"] = {
            "effect": "fog",
            "action": "start",
            "config": {
                "color": "#2a2a2a",
                "density": 0.7,
                "opacity": knobs.fog_opacity,
                "speed": 0.1,
                "mask": False,
            },
        }
    return props


def _palette_for_theme(theme: str) -> str:
    return {
        "dungeon": "stone",
        "cave": "dirt",
        "sewer": "sewer",
        "cathedral": "cathedral",
        "prison": "prison",
        "manor": "manor",
        "street": "street",
        "crypt": "cathedral",
    }.get(theme, "stone")


def dump_map_yaml(properties: dict[str, Any]) -> str:
    return yaml.safe_dump(properties, sort_keys=False, allow_unicode=True)


def write_map_yaml(path: str, properties: dict[str, Any]) -> None:
    from pathlib import Path

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(dump_map_yaml(properties), encoding="utf-8")
