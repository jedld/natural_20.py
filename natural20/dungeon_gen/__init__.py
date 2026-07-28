"""Procedural dungeon generator for Natural20 map YAML."""

from natural20.dungeon_gen.aesthetics import AestheticsReport, analyze_aesthetics
from natural20.dungeon_gen.knobs import (
    GeneratorKnobs,
    ObjectiveSpec,
    knobs_from_theme,
    knobs_json_schema,
)
from natural20.dungeon_gen.pipeline import GenerationResult, generate_dungeon, generate_from_mission
from natural20.dungeon_gen.topology import TraversabilityReport, analyze_traversability

__all__ = [
    "AestheticsReport",
    "GenerationResult",
    "GeneratorKnobs",
    "ObjectiveSpec",
    "TraversabilityReport",
    "analyze_aesthetics",
    "analyze_traversability",
    "generate_dungeon",
    "generate_from_mission",
    "knobs_from_theme",
    "knobs_json_schema",
]
