"""Tests for procedural dungeon generation."""

from __future__ import annotations

import json

import pytest

from natural20.dungeon_gen import (
    GeneratorKnobs,
    ObjectiveSpec,
    analyze_aesthetics,
    analyze_traversability,
    generate_dungeon,
    generate_from_mission,
    knobs_from_theme,
    knobs_json_schema,
)
from natural20.dungeon_gen.export import grid_to_map_properties
from natural20.map_image.grid import map_grid_from_properties


@pytest.mark.parametrize("algorithm", ["bsp", "rooms_graph", "cellular", "hybrid"])
def test_algorithms_produce_walkable_maps(algorithm: str) -> None:
    result = generate_dungeon(
        GeneratorKnobs(
            seed=42,
            algorithm=algorithm,  # type: ignore[arg-type]
            width=36,
            height=28,
            room_count=7,
            ensure_traversable=True,
            enemy_density=0.3,
            trap_density=0.1,
            chest_density=0.2,
        )
    )
    assert result.grid.floor_positions()
    assert result.traversability.reachable_ratio >= 0.5
    assert result.aesthetics.score >= 0.0


def test_objectives_are_placed_and_reachable() -> None:
    knobs = GeneratorKnobs(
        seed=99,
        algorithm="bsp",
        width=40,
        height=30,
        room_count=8,
        objectives=[
            ObjectiveSpec(id="relic", kind="symbol", room_role="treasure", depth="far"),
            ObjectiveSpec(id="informant", kind="npc", npc_type="goblin", room_role="hub", depth="near", dialog=True),
            ObjectiveSpec(id="boss_fight", kind="enemy", room_role="boss", depth="far", hostile=True),
        ],
        ensure_traversable=True,
    )
    result = generate_dungeon(knobs)
    placed_ids = {p.objective_id for p in result.grid.placements if p.objective_id}
    assert "relic" in placed_ids
    assert "informant" in placed_ids
    trav = analyze_traversability(result.grid)
    assert "relic" not in trav.unreachable_objectives


def test_theme_presets_and_schema() -> None:
    knobs = knobs_from_theme("sewer", seed=1, width=32, height=24)
    assert knobs.theme == "sewer"
    schema = knobs_json_schema()
    assert schema["properties"]["algorithm"]["enum"]
    result = generate_from_mission(theme="cave", mission="Find the lost shrine", seed=7, width=30, height=24)
    assert "shrine" in result.properties["description"].lower() or result.properties["description"]


def test_yaml_export_loads_as_map_grid() -> None:
    result = generate_dungeon(GeneratorKnobs(seed=3, width=28, height=22, room_count=6))
    props = grid_to_map_properties(result.grid, result.knobs)
    grid = map_grid_from_properties(props)
    assert grid.width == 28
    assert grid.height == 22
    assert any(grid.cell("base", x, y) == "#" for x in range(grid.width) for y in range(grid.height))
    assert any(grid.cell("base", x, y) == "." for x in range(grid.width) for y in range(grid.height))


def test_aesthetics_report_has_metrics() -> None:
    result = generate_dungeon(GeneratorKnobs(seed=11, width=34, height=26, room_count=7, loop_ratio=0.25))
    report = analyze_aesthetics(result.grid)
    assert 0.0 <= report.score <= 1.0
    assert "floor_ratio" in report.metrics
    assert "traverse" in report.metrics


def test_cli_schema_json() -> None:
    # Ensure schema is JSON serializable
    json.dumps(knobs_json_schema())
