"""Procedural dungeon generation pipeline."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from natural20.dungeon_gen.aesthetics import AestheticsReport, analyze_aesthetics
from natural20.dungeon_gen.export import dump_map_yaml, grid_to_map_properties, write_map_yaml
from natural20.dungeon_gen.knobs import GeneratorKnobs, knobs_from_theme, knobs_json_schema
from natural20.dungeon_gen.layout import generate_layout
from natural20.dungeon_gen.model import DungeonGrid
from natural20.dungeon_gen.placement import assign_room_semantics, place_content
from natural20.dungeon_gen.topology import TraversabilityReport, analyze_traversability


@dataclass
class GenerationResult:
    knobs: GeneratorKnobs
    grid: DungeonGrid
    properties: dict[str, Any]
    traversability: TraversabilityReport
    aesthetics: AestheticsReport
    attempts: int = 1
    accepted: bool = True
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "attempts": self.attempts,
            "messages": self.messages,
            "knobs": self.knobs.to_dict(),
            "traversability": self.traversability.to_dict(),
            "aesthetics": self.aesthetics.to_dict(),
            "rooms": [
                {
                    "id": room.id,
                    "role": room.role,
                    "depth": room.depth,
                    "rect": [room.rect.x, room.rect.y, room.rect.w, room.rect.h],
                    "center": list(room.center),
                }
                for room in self.grid.rooms
            ],
            "critical_path": self.grid.critical_path,
            "placement_count": len(self.grid.placements),
        }

    def yaml(self) -> str:
        return dump_map_yaml(self.properties)

    def write_yaml(self, path: str) -> None:
        write_map_yaml(path, self.properties)


def generate_dungeon(knobs: GeneratorKnobs | dict[str, Any] | None = None, **overrides: Any) -> GenerationResult:
    """Generate a dungeon that satisfies traversability / aesthetics gates when requested."""
    if isinstance(knobs, dict):
        knobs = GeneratorKnobs.from_dict(knobs)
    elif knobs is None:
        knobs = GeneratorKnobs()
    if overrides:
        data = knobs.to_dict()
        data.update(overrides)
        knobs = GeneratorKnobs.from_dict(data)
    knobs = knobs.clamp()

    base_seed = knobs.seed if knobs.seed is not None else random.randint(0, 2**31 - 1)
    best: GenerationResult | None = None

    for attempt in range(1, knobs.max_generation_attempts + 1):
        seed = base_seed + attempt - 1
        rng = random.Random(seed)
        grid = generate_layout(knobs, rng)
        assign_room_semantics(grid, knobs, rng)
        place_content(grid, knobs, rng)
        grid.meta["seed"] = seed
        grid.meta["attempt"] = attempt

        trav = analyze_traversability(
            grid,
            min_reachable_ratio=knobs.min_reachable_floor_ratio,
        )
        aes = analyze_aesthetics(grid)
        props = grid_to_map_properties(grid, knobs)
        result = GenerationResult(
            knobs=knobs,
            grid=grid,
            properties=props,
            traversability=trav,
            aesthetics=aes,
            attempts=attempt,
            accepted=True,
            messages=list(trav.messages) + list(aes.notes),
        )

        # Placement errors
        for err in grid.meta.get("placement_errors", []):
            result.messages.append(err)
            if knobs.objectives:
                result.accepted = False

        if knobs.ensure_traversable and not trav.ok:
            result.accepted = False
        if knobs.min_critical_path_rooms and len(grid.critical_path) < knobs.min_critical_path_rooms:
            if len(grid.rooms) >= knobs.min_critical_path_rooms:
                result.accepted = False
                result.messages.append(
                    f"Critical path rooms {len(grid.critical_path)} "
                    f"< required {knobs.min_critical_path_rooms}"
                )
        if knobs.require_aesthetics_score > 0 and aes.score < knobs.require_aesthetics_score:
            result.accepted = False
            result.messages.append(
                f"Aesthetics score {aes.score:.2f} < required {knobs.require_aesthetics_score:.2f}"
            )

        if best is None or (result.accepted and not best.accepted) or (
            aes.score > best.aesthetics.score and result.accepted == best.accepted
        ):
            best = result

        if result.accepted:
            return result

    assert best is not None
    best.messages.append(
        f"Returned best of {knobs.max_generation_attempts} attempts (gates not fully satisfied)"
    )
    return best


def generate_from_mission(
    *,
    theme: str = "dungeon",
    mission: str = "",
    objectives: list[dict[str, Any]] | None = None,
    **knob_overrides: Any,
) -> GenerationResult:
    """Convenience entry for LLM/campaign builders."""
    knobs = knobs_from_theme(theme, **knob_overrides)
    if mission and not knobs.description:
        knobs.description = mission
    if objectives:
        from natural20.dungeon_gen.knobs import ObjectiveSpec
        from dataclasses import fields

        parsed = []
        for entry in objectives:
            obj_fields = {f.name for f in fields(ObjectiveSpec)}
            parsed.append(ObjectiveSpec(**{k: v for k, v in entry.items() if k in obj_fields}))
        knobs.objectives = parsed
    return generate_dungeon(knobs)


__all__ = [
    "GenerationResult",
    "GeneratorKnobs",
    "generate_dungeon",
    "generate_from_mission",
    "knobs_from_theme",
    "knobs_json_schema",
    "analyze_traversability",
    "analyze_aesthetics",
]
