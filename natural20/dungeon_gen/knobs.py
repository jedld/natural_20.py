"""LLM-controllable knobs for procedural dungeon generation.

These parameters are designed so an LLM (or campaign builder) can express
mission intent without hand-authoring ASCII grids. All values are JSON-serializable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Literal

AlgorithmName = Literal["bsp", "rooms_graph", "cellular", "hybrid"]
ThemeName = Literal[
    "dungeon",
    "cave",
    "sewer",
    "cathedral",
    "prison",
    "manor",
    "street",
    "crypt",
]
RoomRole = Literal[
    "entrance",
    "combat",
    "elite",
    "treasure",
    "shrine",
    "boss",
    "objective",
    "exit",
    "hub",
]


@dataclass
class ObjectiveSpec:
    """A mission-critical placement the generator must satisfy."""

    id: str
    kind: Literal[
        "npc",
        "enemy",
        "chest",
        "trap",
        "teleporter",
        "interactive_object",
        "altar",
        "note",
        "symbol",
        "spawn",
    ] = "interactive_object"
    room_role: RoomRole | None = None
    """Prefer a room with this semantic role (boss, treasure, …)."""
    depth: Literal["near", "mid", "far", "any"] = "any"
    """Relative distance along the critical path from the entrance."""
    npc_type: str | None = None
    label: str | None = None
    group: str = "b"
    hostile: bool = False
    dialog: bool = False
    target_map: str | None = None
    """For teleporters: game.yml map key."""
    inventory: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    required: bool = True
    """If true, generation fails (or retries) when placement is impossible."""


@dataclass
class GeneratorKnobs:
    """Top-level control surface for the dungeon generator."""

    # --- Determinism & size ---
    seed: int | None = None
    width: int = 40
    height: int = 30
    algorithm: AlgorithmName = "hybrid"

    # --- Layout shape (BSP / rooms_graph) ---
    room_count: int = 8
    room_min_size: int = 5
    room_max_size: int = 11
    corridor_width: int = 1
    loop_ratio: float = 0.18
    """Fraction of non-MST Delaunay edges re-added as shortcut loops (Binding of Isaac style)."""
    linearity: float = 0.35
    """0 = many loops/branches, 1 = prefer a single critical path (more linear)."""
    padding: int = 1
    """Wall padding between rooms and map edge."""

    # --- Cellular / cave ---
    cave_fill_chance: float = 0.45
    cave_iterations: int = 5
    cave_birth_limit: int = 4
    cave_death_limit: int = 3

    # --- Hybrid mix ---
    hybrid_cave_wing_chance: float = 0.35
    """Chance to grow a cellular cave wing off a far room."""

    # --- Theme & atmosphere ---
    theme: ThemeName = "dungeon"
    illumination: float = 0.55
    fog: bool = False
    fog_opacity: float = 0.45
    water_chance: float = 0.0
    """Chance to flood low/peripheral floor tiles as water."""

    # --- Encounter dressing densities (0–1) ---
    enemy_density: float = 0.35
    trap_density: float = 0.15
    chest_density: float = 0.2
    door_chance: float = 0.55
    secret_passage_chance: float = 0.08
    light_density: float = 0.25

    # --- Default enemy roster (weighted by order) ---
    enemy_types: list[str] = field(default_factory=lambda: ["goblin", "skeleton", "wolf"])
    elite_types: list[str] = field(default_factory=lambda: ["hobgoblin", "ogre"])
    boss_types: list[str] = field(default_factory=lambda: ["bugbear"])

    # --- Mission / quest placements ---
    objectives: list[ObjectiveSpec] = field(default_factory=list)
    place_entrance_spawn: bool = True
    place_exit_teleporter: bool = False
    exit_target_map: str | None = None
    exit_target_position: list[int] | None = None
    enemy_group: str = "b"
    player_group: str = "a"

    # --- Quality gates ---
    ensure_traversable: bool = True
    min_reachable_floor_ratio: float = 0.92
    min_critical_path_rooms: int = 3
    max_generation_attempts: int = 12
    require_aesthetics_score: float = 0.0
    """0 disables; otherwise reject maps scoring below this (0–1)."""

    # --- Metadata ---
    name: str = "Generated Dungeon"
    description: str = ""
    map_id: str = "generated_dungeon"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "GeneratorKnobs":
        known = {f.name for f in fields(cls)}
        payload = {k: v for k, v in raw.items() if k in known}
        objectives = []
        for entry in payload.pop("objectives", []) or []:
            if isinstance(entry, ObjectiveSpec):
                objectives.append(entry)
            elif isinstance(entry, dict):
                obj_fields = {f.name for f in fields(ObjectiveSpec)}
                objectives.append(ObjectiveSpec(**{k: v for k, v in entry.items() if k in obj_fields}))
        knobs = cls(**payload)
        knobs.objectives = objectives
        return knobs

    def clamp(self) -> "GeneratorKnobs":
        """Return a copy with values coerced into safe ranges."""
        data = self.to_dict()
        data["width"] = max(16, min(120, int(self.width)))
        data["height"] = max(12, min(90, int(self.height)))
        data["room_count"] = max(3, min(40, int(self.room_count)))
        data["room_min_size"] = max(3, min(20, int(self.room_min_size)))
        data["room_max_size"] = max(data["room_min_size"], min(24, int(self.room_max_size)))
        data["corridor_width"] = max(1, min(3, int(self.corridor_width)))
        data["loop_ratio"] = max(0.0, min(0.8, float(self.loop_ratio)))
        data["linearity"] = max(0.0, min(1.0, float(self.linearity)))
        for key in (
            "enemy_density",
            "trap_density",
            "chest_density",
            "door_chance",
            "secret_passage_chance",
            "water_chance",
            "light_density",
            "hybrid_cave_wing_chance",
            "illumination",
            "fog_opacity",
            "min_reachable_floor_ratio",
            "require_aesthetics_score",
            "cave_fill_chance",
        ):
            data[key] = max(0.0, min(1.0, float(data[key])))
        data["objectives"] = self.objectives
        return GeneratorKnobs.from_dict(data)


def knobs_json_schema() -> dict[str, Any]:
    """JSON Schema for LLM tool / function-calling surfaces."""
    return {
        "type": "object",
        "title": "DungeonGeneratorKnobs",
        "description": (
            "Controls for Natural20 procedural dungeon generation. "
            "Tune layout, theme, densities, and mission objectives so the map "
            "supports the campaign quest."
        ),
        "properties": {
            "seed": {"type": ["integer", "null"]},
            "width": {"type": "integer", "minimum": 16, "maximum": 120},
            "height": {"type": "integer", "minimum": 12, "maximum": 90},
            "algorithm": {
                "type": "string",
                "enum": ["bsp", "rooms_graph", "cellular", "hybrid"],
                "description": (
                    "bsp: classic Rogue-style rooms; rooms_graph: scatter+MST+loops "
                    "(Isaac-like); cellular: caves (DF/Spelunky); hybrid: BSP rooms "
                    "with optional cave wing"
                ),
            },
            "room_count": {"type": "integer", "minimum": 3, "maximum": 40},
            "loop_ratio": {
                "type": "number",
                "minimum": 0,
                "maximum": 0.8,
                "description": "Extra corridor loops beyond the spanning tree",
            },
            "linearity": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Higher = more forced critical path / less branching",
            },
            "theme": {
                "type": "string",
                "enum": [
                    "dungeon",
                    "cave",
                    "sewer",
                    "cathedral",
                    "prison",
                    "manor",
                    "street",
                    "crypt",
                ],
            },
            "enemy_density": {"type": "number", "minimum": 0, "maximum": 1},
            "trap_density": {"type": "number", "minimum": 0, "maximum": 1},
            "chest_density": {"type": "number", "minimum": 0, "maximum": 1},
            "enemy_types": {"type": "array", "items": {"type": "string"}},
            "objectives": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "kind"],
                    "properties": {
                        "id": {"type": "string"},
                        "kind": {
                            "type": "string",
                            "enum": [
                                "npc",
                                "enemy",
                                "chest",
                                "trap",
                                "teleporter",
                                "interactive_object",
                                "altar",
                                "note",
                                "symbol",
                                "spawn",
                            ],
                        },
                        "room_role": {
                            "type": ["string", "null"],
                            "enum": [
                                "entrance",
                                "combat",
                                "elite",
                                "treasure",
                                "shrine",
                                "boss",
                                "objective",
                                "exit",
                                "hub",
                                None,
                            ],
                        },
                        "depth": {
                            "type": "string",
                            "enum": ["near", "mid", "far", "any"],
                        },
                        "npc_type": {"type": ["string", "null"]},
                        "label": {"type": ["string", "null"]},
                        "required": {"type": "boolean"},
                    },
                },
            },
            "ensure_traversable": {"type": "boolean"},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "map_id": {"type": "string"},
        },
        "additionalProperties": True,
    }


THEME_PRESETS: dict[str, dict[str, Any]] = {
    "dungeon": {
        "algorithm": "bsp",
        "theme": "dungeon",
        "illumination": 0.5,
        "enemy_types": ["goblin", "skeleton"],
        "elite_types": ["hobgoblin"],
        "boss_types": ["bugbear"],
    },
    "cave": {
        "algorithm": "cellular",
        "theme": "cave",
        "illumination": 0.35,
        "fog": True,
        "water_chance": 0.12,
        "enemy_types": ["wolf", "bat"],
        "elite_types": ["owlbear"],
        "boss_types": ["ogre"],
        "door_chance": 0.1,
    },
    "sewer": {
        "algorithm": "hybrid",
        "theme": "sewer",
        "illumination": 0.3,
        "fog": True,
        "water_chance": 0.28,
        "trap_density": 0.22,
        "enemy_types": ["rat_swarm", "skeleton"],
        "palette_hint": "sewer",
    },
    "cathedral": {
        "algorithm": "bsp",
        "theme": "cathedral",
        "illumination": 0.6,
        "linearity": 0.55,
        "chest_density": 0.12,
        "enemy_types": ["skeleton"],
        "boss_types": ["bugbear"],
        "palette_hint": "cathedral",
    },
    "prison": {
        "algorithm": "bsp",
        "theme": "prison",
        "linearity": 0.65,
        "door_chance": 0.85,
        "trap_density": 0.2,
        "enemy_types": ["guard", "skeleton"],
        "palette_hint": "prison",
    },
    "manor": {
        "algorithm": "rooms_graph",
        "theme": "manor",
        "room_min_size": 6,
        "illumination": 0.65,
        "enemy_types": ["skeleton"],
        "palette_hint": "manor",
    },
    "street": {
        "algorithm": "rooms_graph",
        "theme": "street",
        "loop_ratio": 0.35,
        "linearity": 0.2,
        "door_chance": 0.2,
        "palette_hint": "street",
    },
    "crypt": {
        "algorithm": "hybrid",
        "theme": "crypt",
        "illumination": 0.25,
        "fog": True,
        "trap_density": 0.25,
        "enemy_types": ["skeleton", "zombie"],
        "boss_types": ["wight"],
    },
}


def knobs_from_theme(theme: str, **overrides: Any) -> GeneratorKnobs:
    preset = dict(THEME_PRESETS.get(theme, THEME_PRESETS["dungeon"]))
    preset.pop("palette_hint", None)
    preset.update(overrides)
    preset.setdefault("theme", theme if theme in THEME_PRESETS else "dungeon")
    return GeneratorKnobs.from_dict(preset).clamp()
