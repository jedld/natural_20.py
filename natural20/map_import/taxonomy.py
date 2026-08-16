"""Battlemap tile classes and Natural20 legend/token mappings.

Keep object `type` keys in the bundled `templates/items/objects.yml` catalogue
so imported maps pass `scripts/validate_campaign.py`. Furniture that has no
dedicated SRD object uses `barrel` (half cover) with a human-readable name.
Stairs are recorded as notes plus a wiring TODO until a destination map exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from natural20.map_import.ink import EdgeBits

TileClass = Literal[
    "wall",
    "floor",
    "void",
    "water",
    "door",
    "object",
    "unknown",
]

ObjectSubtype = Literal[
    "none",
    "wooden_door",
    "chest",
    "barrel",
    "table",
    "chair",
    "bed",
    "bookshelf",
    "statue",
    "column",
    "fireplace",
    "campfire",
    "brazier",
    "tree",
    "pit",
    "chasm",
    "window",
    "stairs",
    "switch",
    "note",
    "altar",
    "other",
]

TILE_CLASSES: tuple[str, ...] = (
    "wall",
    "floor",
    "void",
    "water",
    "door",
    "object",
    "unknown",
)

OBJECT_SUBTYPES: tuple[str, ...] = (
    "none",
    "wooden_door",
    "chest",
    "barrel",
    "table",
    "chair",
    "bed",
    "bookshelf",
    "statue",
    "column",
    "fireplace",
    "campfire",
    "brazier",
    "tree",
    "pit",
    "chasm",
    "window",
    "stairs",
    "switch",
    "note",
    "altar",
    "other",
)

# Subtypes that live on the object layer rather than rewriting the base tile.
OBJECT_LAYER_SUBTYPES = {
    "chest",
    "barrel",
    "table",
    "chair",
    "bed",
    "bookshelf",
    "statue",
    "fireplace",
    "campfire",
    "brazier",
    "tree",
    "window",
    "stairs",
    "switch",
    "note",
    "altar",
    "other",
}

HARDCODED_BASE = {".", "#", "_", "-", "|"}

_FURNITURE_AS_BARREL = {"table", "chair", "bed", "bookshelf", "statue", "altar"}

# N, E, S, W
_DIRECTIONAL_WALLS: dict[tuple[int, int, int, int], tuple[str, str, str]] = {
    (1, 0, 0, 1): ("┌", "stone_wall_tl", "Stone Wall Thin Top Left"),
    (1, 0, 0, 0): ("┬", "stone_wall_t", "Stone Wall Thin Top"),
    (1, 1, 0, 0): ("┐", "stone_wall_tr", "Stone Wall Thin Top Right"),
    (0, 1, 0, 0): ("┤", "stone_wall_r", "Stone Wall Thin Right"),
    (0, 0, 0, 1): ("├", "stone_wall_l", "Stone Wall Thin Left"),
    (0, 0, 1, 0): ("┴", "stone_wall_b", "Stone Wall Thin Bottom"),
    (0, 1, 1, 0): ("┘", "stone_wall_br", "Stone Wall Thin Bottom Right"),
    (0, 0, 1, 1): ("└", "stone_wall_bl", "Stone Wall Thin Bottom Left"),
    (1, 0, 1, 0): ("Z", "stone_wall_tb", "Stone Wall Thin Top Bottom"),
    (0, 1, 0, 1): ("H", "stone_wall_lr", "Stone Wall Thin Left Right"),
}

DIRECTIONAL_WALL_TOKENS = frozenset(token for token, _typ, _name in _DIRECTIONAL_WALLS.values())

_CORNER_DOORS = {
    ("N", "W"): ("╒", "corner_door_tl", "Corner Door Top Left"),
    ("N", "E"): ("╗", "corner_door_tr", "Corner Door Top Right"),
    ("S", "W"): ("╚", "corner_door_bl", "Corner Door Bottom Left"),
    ("S", "E"): ("╝", "corner_door_br", "Corner Door Bottom Right"),
    ("W", "N"): ("╒", "corner_door_tl", "Corner Door Top Left"),
    ("E", "N"): ("╗", "corner_door_tr", "Corner Door Top Right"),
    ("W", "S"): ("╚", "corner_door_bl", "Corner Door Bottom Left"),
    ("E", "S"): ("╝", "corner_door_br", "Corner Door Bottom Right"),
}

_SUBTYPE_ALIASES = {
    "door": "wooden_door",
    "wooden door": "wooden_door",
    "doorway": "wooden_door",
    "archway": "wooden_door",
    "treasure chest": "chest",
    "crate": "barrel",
    "cask": "barrel",
    "desk": "table",
    "bench": "chair",
    "stool": "chair",
    "cot": "bed",
    "shelf": "bookshelf",
    "bookcase": "bookshelf",
    "pillar": "column",
    "hearth": "fireplace",
    "fire": "campfire",
    "torch": "brazier",
    "pit trap": "pit",
    "trap": "pit",
    "hole": "pit",
    "stairs up": "stairs",
    "stairs down": "stairs",
    "staircase": "stairs",
    "ladder": "stairs",
    "lever": "switch",
    "button": "switch",
    "scroll": "note",
    "book": "note",
    "empty": "none",
    "ground": "none",
    "floor": "none",
    "stone": "none",
    "cobble": "none",
}


@dataclass(frozen=True)
class TokenMapping:
    """How a classified tile becomes Natural20 YAML."""

    base_token: str
    object_token: str | None = None
    object_type: str | None = None
    object_name: str | None = None
    layer: str = "base"
    needs_wiring: bool = False
    notes: str = ""


def normalize_class(raw: str | None) -> TileClass:
    value = (raw or "unknown").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "stone_wall": "wall",
        "walls": "wall",
        "solid": "wall",
        "ground": "floor",
        "empty": "floor",
        "open": "floor",
        "passable": "floor",
        "outside": "void",
        "blank": "void",
        "none": "void",
        "pool": "water",
        "river": "water",
        "doorway": "door",
        "arch": "door",
        "furniture": "object",
        "item": "object",
        "prop": "object",
        "feature": "object",
    }
    value = aliases.get(value, value)
    if value in TILE_CLASSES:
        return value  # type: ignore[return-value]
    return "unknown"


def normalize_subtype(raw: str | None) -> ObjectSubtype:
    value = (raw or "none").strip().lower()
    value = _SUBTYPE_ALIASES.get(value, value)
    value = value.replace("-", "_").replace(" ", "_")
    value = _SUBTYPE_ALIASES.get(value, value)
    if value in OBJECT_SUBTYPES:
        return value  # type: ignore[return-value]
    return "other"


def mapping_for_wall_edges(north: bool, east: bool, south: bool, west: bool) -> TokenMapping | None:
    """Legend mapping for a 1–2 sided thin wall, or None for solid/empty/3+ sides."""
    key = (int(bool(north)), int(bool(east)), int(bool(south)), int(bool(west)))
    if key not in _DIRECTIONAL_WALLS:
        return None
    token, typ, name = _DIRECTIONAL_WALLS[key]
    return TokenMapping(base_token=token, object_type=typ, object_name=name)


def directional_wall_mappings() -> tuple[TokenMapping, ...]:
    return tuple(
        TokenMapping(base_token=token, object_type=typ, object_name=name)
        for token, typ, name in _DIRECTIONAL_WALLS.values()
    )


def wall_token_edges(token: str) -> tuple[int, int, int, int] | None:
    """N,E,S,W bits for a directional wall glyph, or None."""
    for key, (tok, _typ, _name) in _DIRECTIONAL_WALLS.items():
        if tok == token:
            return key
    return None


def mapping_for(
    tile_class: TileClass,
    subtype: ObjectSubtype = "none",
    *,
    orientation: str | None = None,
    edges: EdgeBits | None = None,
) -> TokenMapping:
    """Map a classification onto base/object tokens."""
    if edges and (edges.any_door() or edges.any_wall() or edges.solid):
        edge_map = _mapping_from_edges(edges, orientation=orientation)
        if edge_map is not None:
            # Preserve furniture/objects on walkable cells that also have a thin wall.
            if tile_class == "object" and subtype not in {"none", "wooden_door", "other"} and not edges.solid:
                obj = mapping_for(tile_class, subtype, orientation=orientation)
                if obj.object_token:
                    return TokenMapping(
                        base_token=edge_map.base_token,
                        object_token=obj.object_token,
                        object_type=obj.object_type,
                        object_name=obj.object_name,
                        layer="base_1",
                        needs_wiring=obj.needs_wiring,
                        notes=obj.notes,
                    )
            return edge_map
    if tile_class == "wall":
        if subtype == "column":
            return TokenMapping(base_token="#", notes="column treated as wall")
        return TokenMapping(base_token="#")
    if tile_class == "void":
        return TokenMapping(base_token="_")
    if tile_class == "water":
        return TokenMapping(
            base_token=".",
            object_token="w",
            object_type="water",
            object_name="Pool of water",
            layer="base_1",
        )
    if tile_class == "door" or subtype == "wooden_door":
        token = "|" if (orientation or "").startswith("v") else "-"
        return TokenMapping(base_token=token, object_type="wooden_door", object_name="Door")
    if tile_class in {"floor", "unknown"} and subtype in {"none", "other"} and tile_class != "object":
        return TokenMapping(base_token=".")

    if subtype == "chest":
        return TokenMapping(".", "c", "chest", "Chest", "base_1")
    if subtype == "barrel":
        return TokenMapping(".", "b", "barrel", "Barrel", "base_1")
    if subtype in _FURNITURE_AS_BARREL:
        return TokenMapping(".", "F", "barrel", subtype.replace("_", " ").title(), "base_1")
    if subtype == "column":
        return TokenMapping("#")
    if subtype == "fireplace":
        return TokenMapping(".", "f", "campfire", "Fireplace", "base_1")
    if subtype == "campfire":
        return TokenMapping(".", "f", "campfire", "Campfire", "base_1")
    if subtype == "brazier":
        return TokenMapping(".", "Z", "brazier", "Brazier", "base_1")
    if subtype == "tree":
        return TokenMapping(".", "t", "tree", "Tree", "base_1")
    if subtype == "pit":
        return TokenMapping(".", "P", "bottomless_pit", "Pit", "base_1")
    if subtype == "chasm":
        return TokenMapping(".", "C", "chasm", "Chasm", "base_1")
    if subtype == "window":
        return TokenMapping(".", "W", "window", "Window", "base_1")
    if subtype == "stairs":
        return TokenMapping(
            ".",
            "S",
            "note",
            "Stairs",
            "base_1",
            needs_wiring=True,
            notes="Stairs detected — wire a teleporter after choosing the destination map",
        )
    if subtype == "switch":
        return TokenMapping(".", "s", "switch", "Switch", "base_1")
    if subtype == "note":
        return TokenMapping(".", "n", "note", "Note", "base_1")
    if tile_class == "object":
        return TokenMapping(".", "F", "barrel", "Object", "base_1")
    return TokenMapping(base_token=".")


def _mapping_from_edges(edges: EdgeBits, *, orientation: str | None = None) -> TokenMapping | None:
    if edges.solid or edges.wall_tuple() == (1, 1, 1, 1):
        return TokenMapping(base_token="#")
    door_side = edges.door_side()
    if door_side:
        walls = [s for s in ("N", "E", "S", "W") if getattr(edges, s) and s != door_side]
        for wall_side in walls:
            key = (door_side, wall_side)
            if key in _CORNER_DOORS:
                token, typ, name = _CORNER_DOORS[key]
                return TokenMapping(base_token=token, object_type=typ, object_name=name)
        if door_side in {"E", "W"} or (orientation or "").startswith("v"):
            return TokenMapping(base_token="|", object_type="wooden_door", object_name="Door")
        return TokenMapping(base_token="-", object_type="wooden_door", object_name="Door")
    if edges.any_wall():
        key = edges.wall_tuple()
        if key in _DIRECTIONAL_WALLS:
            token, typ, name = _DIRECTIONAL_WALLS[key]
            return TokenMapping(base_token=token, object_type=typ, object_name=name)
        return TokenMapping(base_token="#")
    return None


def legend_entry(mapping: TokenMapping) -> dict[str, Any] | None:
    if not mapping.object_type:
        return None
    if mapping.base_token in HARDCODED_BASE and not mapping.object_token:
        return None
    entry: dict[str, Any] = {
        "name": mapping.object_name or mapping.object_type,
        "type": mapping.object_type,
    }
    if mapping.object_type == "campfire":
        entry["light"] = {"bright": 20, "dim": 10}
    if mapping.object_type == "note":
        entry["notes"] = [{"note": mapping.object_name or "Feature"}]
    return entry
