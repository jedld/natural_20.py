#!/usr/bin/env python3
"""Rebuild outcasts_path maps with procedural layouts while preserving story content."""

from __future__ import annotations

import copy
import shutil
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from natural20.dungeon_gen import GeneratorKnobs, ObjectiveSpec, generate_dungeon
from natural20.dungeon_gen.export import grid_to_map_properties
from natural20.dungeon_gen.model import FLOOR, DungeonGrid, Room
from natural20.map_image.batch import batch_render_missing_map_assets
from natural20.yaml_loader import load_yaml

CAMPAIGN = REPO / "user_levels" / "outcasts_path"
MAPS = CAMPAIGN / "maps"
BACKUP = CAMPAIGN / ".map_rebuild_backup"


def _load_old(name: str) -> dict:
    """Prefer story seed from backup (original entity dialogs), else current maps."""
    backup_path = BACKUP / f"{name}.yml"
    path = MAPS / f"{name}.yml"
    if backup_path.is_file():
        return load_yaml(backup_path, campaign_root=CAMPAIGN)
    return load_yaml(path, campaign_root=CAMPAIGN)


def _index_entities(old: dict) -> dict[str, dict]:
    entities = (old.get("map") or {}).get("entities") or []
    by_name = {}
    for ent in entities:
        key = ent.get("name") or ent.get("token")
        if key:
            by_name[str(key)] = ent
    return by_name


def _free_tiles(grid: DungeonGrid, room: Room, occupied: set[tuple[int, int]]) -> list[tuple[int, int]]:
    tiles = []
    for x, y in room.rect.floor_cells():
        if not grid.in_bounds(x, y):
            continue
        if grid.cells[x][y] != FLOOR:
            continue
        if (x, y) in occupied:
            continue
        tiles.append((x, y))
    # Prefer interior
    tiles.sort(key=lambda p: abs(p[0] - room.center[0]) + abs(p[1] - room.center[1]))
    return tiles


def _pick_room(grid: DungeonGrid, role: str | None = None, depth: str = "any") -> Room:
    rooms = list(grid.rooms)
    if role:
        matched = [r for r in rooms if r.role == role]
        if matched:
            rooms = matched
    max_depth = max((r.depth for r in grid.rooms), default=1) or 1
    if depth != "any":
        filtered = []
        for room in rooms:
            ratio = room.depth / max_depth
            if depth == "near" and ratio <= 0.34:
                filtered.append(room)
            elif depth == "mid" and 0.34 < ratio <= 0.7:
                filtered.append(room)
            elif depth == "far" and ratio > 0.7:
                filtered.append(room)
        if filtered:
            rooms = filtered
    return rooms[0] if rooms else grid.rooms[0]


def _place(
    grid: DungeonGrid,
    occupied: set[tuple[int, int]],
    *,
    room: Room,
    entity: dict,
    layer: str | None = None,
) -> tuple[int, int]:
    tiles = _free_tiles(grid, room, occupied)
    if not tiles:
        # fallback any floor
        for x in range(grid.width):
            for y in range(grid.height):
                if grid.cells[x][y] == FLOOR and (x, y) not in occupied:
                    tiles = [(x, y)]
                    break
            if tiles:
                break
    if not tiles:
        raise RuntimeError(f"No free tile for {entity.get('name')}")
    pos = tiles[len(tiles) // 3] if len(tiles) > 3 else tiles[0]
    occupied.add(pos)
    ent = copy.deepcopy(entity)
    ent["pos"] = [pos[0], pos[1]]
    if layer:
        ent["layer"] = layer
    elif entity.get("type") in {"teleporter", "interactive_object", "note", "chest"} or entity.get("layer") == "object":
        ent["layer"] = "object"
    grid.meta.setdefault("story_entities", []).append(ent)
    return pos


def _strip_generic_placements(grid: DungeonGrid) -> None:
    """Keep doors/water from generator; drop generic enemies/chests/traps/lights/spawns."""
    keep = []
    for p in grid.placements:
        if p.kind in {"door"}:
            keep.append(p)
    grid.placements = keep
    grid.meta.pop("player_spawn_points", None)


def _apply_story(grid: DungeonGrid, knobs: GeneratorKnobs, old: dict, placements: list[tuple[str, str, str | None]]) -> dict[str, tuple[int, int]]:
    """placements: list of (entity_name, room_role, depth). Returns name->pos."""
    _strip_generic_placements(grid)
    old_ents = _index_entities(old)
    occupied: set[tuple[int, int]] = set()
    positions: dict[str, tuple[int, int]] = {}

    # Reserve spawn in entrance
    entrance = grid.room_by_id(grid.entrance_room_id) if grid.entrance_room_id is not None else grid.rooms[0]
    spawn_tiles = _free_tiles(grid, entrance, occupied)
    spawn = spawn_tiles[0] if spawn_tiles else entrance.center
    occupied.add(spawn)
    grid.meta["player_spawn_points"] = [{"position": [spawn[0], spawn[1]], "group": "a"}]
    # Multiple spawn points for party of 4
    for dx, dy in ((1, 0), (0, 1), (-1, 0)):
        sx, sy = spawn[0] + dx, spawn[1] + dy
        if grid.in_bounds(sx, sy) and grid.cells[sx][sy] == FLOOR and (sx, sy) not in occupied:
            occupied.add((sx, sy))
            grid.meta["player_spawn_points"].append({"position": [sx, sy], "group": "a"})
    positions["__spawn__"] = spawn

    for name, role, depth in placements:
        ent = old_ents.get(name)
        if not ent:
            print(f"  warning: missing old entity {name}")
            continue
        room = _pick_room(grid, role, depth or "any")
        pos = _place(grid, occupied, room=room, entity=ent)
        positions[name] = pos
    return positions


def _build_map(name: str, knobs: GeneratorKnobs, old: dict, story: list[tuple[str, str, str | None]]) -> tuple[dict, dict[str, tuple[int, int]]]:
    result = generate_dungeon(knobs)
    positions = _apply_story(result.grid, knobs, old, story)
    props = grid_to_map_properties(result.grid, knobs)

    # Preserve campaign narration / effects / name
    for key in ("name", "description", "narration", "default_effect", "point_fires", "lights"):
        if key in old and old[key] is not None:
            props[key] = copy.deepcopy(old[key])

    # Replace entities with story placements; rebuild legend from them
    entities = result.grid.meta.get("story_entities") or []
    props["map"]["entities"] = entities
    legend = {"w": {"name": "Pool of water", "type": "water"}}
    old_legend = old.get("legend") or {}
    for ent in entities:
        token = ent["token"]
        legend[token] = copy.deepcopy(old_legend.get(token) or {
            "name": ent.get("name", token),
            "type": ent.get("type"),
            "sub_type": ent.get("sub_type"),
            "group": ent.get("group"),
        })
        # Ensure teleporter legend has targets from entity
        if ent.get("type") == "teleporter":
            legend[token]["type"] = "teleporter"
            if ent.get("target_map"):
                legend[token]["target_map"] = ent["target_map"]
            if ent.get("target_position"):
                legend[token]["target_position"] = ent["target_position"]
        if ent.get("type") == "npc":
            legend[token]["type"] = "npc"
            legend[token]["sub_type"] = ent.get("sub_type")
            legend[token]["group"] = ent.get("group", "b")
            if ent.get("overrides"):
                legend[token]["overrides"] = ent["overrides"]
    props["legend"] = legend
    props["player_spawn_points"] = result.grid.meta["player_spawn_points"]
    props["background_image"] = f"{name}.png"
    props["render"] = {"palette": knobs.theme if knobs.theme != "dungeon" else "stone", "tile_size": 50}
    # Theme palette mapping
    palette_map = {
        "street": "street",
        "manor": "manor",
        "sewer": "sewer",
        "prison": "prison",
        "cathedral": "cathedral",
        "cave": "dirt",
        "tavern": "street",
    }
    props["render"]["palette"] = palette_map.get(knobs.theme, "stone")
    props["_generator"] = result.properties.get("_generator")
    props["_generator"]["story_seed"] = knobs.seed
    return props, positions


def rebuild() -> None:
    BACKUP.mkdir(parents=True, exist_ok=True)
    # Only seed backup once so original story entities remain the source of truth.
    for path in MAPS.glob("*.yml"):
        if path.name == "monsters.yml":
            continue
        dest = BACKUP / path.name
        if not dest.exists():
            shutil.copy2(path, dest)

    old = {name: _load_old(name) for name in (
        "city_gate", "city_streets", "tavern", "investigator_manor", "sewers", "prison", "cathedral"
    )}

    built: dict[str, dict] = {}
    positions: dict[str, dict[str, tuple[int, int]]] = {}

    specs = {
        "city_gate": (
            GeneratorKnobs(
                seed=2401,
                algorithm="rooms_graph",
                theme="street",
                width=24,
                height=14,
                room_count=5,
                loop_ratio=0.25,
                linearity=0.4,
                enemy_density=0.0,
                trap_density=0.0,
                chest_density=0.0,
                door_chance=0.35,
                water_chance=0.0,
                illumination=0.75,
                name="Thyros City Gate",
                ensure_traversable=True,
                min_critical_path_rooms=2,
            ),
            [
                ("city_guard", "hub", "mid"),
                ("direction_sign", "hub", "mid"),
                ("transition_to_streets", "exit", "far"),
            ],
        ),
        "city_streets": (
            GeneratorKnobs(
                seed=2402,
                algorithm="rooms_graph",
                theme="street",
                width=28,
                height=20,
                room_count=10,
                loop_ratio=0.4,
                linearity=0.15,
                enemy_density=0.0,
                trap_density=0.05,
                chest_density=0.05,
                door_chance=0.25,
                illumination=0.7,
                fog=True,
                fog_opacity=0.35,
                name="Thyros City Streets",
                ensure_traversable=True,
                min_critical_path_rooms=3,
            ),
            [
                ("whisper", "hub", "near"),
                ("detective_jaro", "hub", "mid"),
                ("tavern_entrance", "hub", "near"),
                ("transition_to_manor", "combat", "mid"),
                ("transition_to_prison", "combat", "mid"),
                ("transition_to_cathedral", "exit", "far"),
                ("sewer_entrance", "elite", "far"),
                # return to gate — synthesized if missing
            ],
        ),
        "investigator_manor": (
            GeneratorKnobs(
                seed=2403,
                algorithm="bsp",
                theme="manor",
                width=20,
                height=16,
                room_count=7,
                loop_ratio=0.2,
                linearity=0.45,
                enemy_density=0.0,
                trap_density=0.0,
                chest_density=0.15,
                door_chance=0.6,
                illumination=0.55,
                name="Reed's Manor",
                ensure_traversable=True,
            ),
            [
                ("marcus_reed", "hub", "mid"),
                ("manor_notes", "treasure", "mid"),
                ("investigator_badge", "treasure", "mid"),
                ("city_map", "shrine", "far"),
                ("exit_to_streets", "entrance", "near"),
            ],
        ),
        "sewers": (
            GeneratorKnobs(
                seed=2404,
                algorithm="hybrid",
                theme="sewer",
                width=24,
                height=16,
                room_count=8,
                loop_ratio=0.22,
                linearity=0.35,
                enemy_density=0.0,  # story enemies placed manually
                trap_density=0.2,
                chest_density=0.1,
                door_chance=0.2,
                water_chance=0.25,
                illumination=0.3,
                fog=True,
                fog_opacity=0.55,
                name="Thyros Sewers",
                ensure_traversable=True,
                min_critical_path_rooms=3,
            ),
            [
                ("sewer_guard_1", "combat", "mid"),
                ("sewer_guard_2", "elite", "mid"),
                ("rat_swarm", "combat", "near"),
                ("rat_swarm_2", "combat", "mid"),
                ("sewer_symbol", "treasure", "far"),
                ("exit_to_streets", "entrance", "near"),
                ("deep_sewer", "exit", "far"),
            ],
        ),
        "prison": (
            GeneratorKnobs(
                seed=2405,
                algorithm="bsp",
                theme="prison",
                width=20,
                height=16,
                room_count=7,
                loop_ratio=0.12,
                linearity=0.65,
                enemy_density=0.0,
                trap_density=0.15,
                chest_density=0.05,
                door_chance=0.85,
                illumination=0.45,
                name="Thyros City Prison",
                ensure_traversable=True,
            ),
            [
                ("prison_guard", "elite", "mid"),
                ("prisoner", "treasure", "far"),
                ("prison_ledger", "treasure", "mid"),
                ("secret_passage", "exit", "far"),
                ("exit_to_streets", "entrance", "near"),
            ],
        ),
        "cathedral": (
            GeneratorKnobs(
                seed=2406,
                algorithm="bsp",
                theme="cathedral",
                width=22,
                height=18,
                room_count=8,
                loop_ratio=0.15,
                linearity=0.55,
                enemy_density=0.0,
                trap_density=0.1,
                chest_density=0.1,
                door_chance=0.5,
                illumination=0.55,
                name="Saint Elara Cathedral",
                ensure_traversable=True,
                min_critical_path_rooms=3,
            ),
            [
                ("lady_ophelia", "boss", "far"),
                ("kester_volo", "boss", "far"),
                ("ritual_candle_1", "shrine", "mid"),
                ("ritual_candle_2", "shrine", "mid"),
                ("ritual_candle_3", "shrine", "far"),
                ("ritual_candle_4", "shrine", "far"),
                ("ritual_candle_5", "shrine", "far"),
                ("ritual_altar", "shrine", "far"),
                ("society_member_1", "elite", "mid"),
                ("society_member_2", "elite", "mid"),
                ("society_member_3", "combat", "mid"),
                ("society_member_4", "combat", "mid"),
                ("exit_to_streets", "entrance", "near"),
                ("hidden_passage", "exit", "far"),
            ],
        ),
    }

    for map_id, (knobs, story) in specs.items():
        print(f"Generating {map_id}...")
        props, pos = _build_map(map_id, knobs, old[map_id], story)
        built[map_id] = props
        positions[map_id] = pos

    # Add return-to-gate teleporter on streets if absent
    streets_ents = {e.get("name"): e for e in built["city_streets"]["map"]["entities"]}
    if "transition_to_gate" not in streets_ents and "return_to_gate" not in streets_ents:
        gate_spawn = positions["city_gate"]["__spawn__"]
        # place near streets spawn
        spawn = positions["city_streets"]["__spawn__"]
        ent = {
            "token": "TG",
            "layer": "object",
            "pos": [spawn[0], spawn[1]],
            "name": "transition_to_gate",
            "type": "teleporter",
            "target_map": "city_gate",
            "visible": True,
            "target_position": [gate_spawn[0], gate_spawn[1]],
            "overrides": {
                "label": "City Gate",
                "description": "The road back to Thyros's main gate.",
            },
        }
        # nudge off spawn
        ent["pos"] = [min(spawn[0] + 2, built["city_streets"]["map"]["size"][0] - 2), spawn[1]]
        built["city_streets"]["map"]["entities"].append(ent)
        built["city_streets"]["legend"]["TG"] = {
            "name": "City Gate",
            "type": "teleporter",
            "target_map": "city_gate",
            "target_position": [gate_spawn[0], gate_spawn[1]],
        }
        positions["city_streets"]["transition_to_gate"] = tuple(ent["pos"])

    # Wire teleporter destinations to destination spawn / exit pads
    def set_tp(src_map: str, ent_name: str, dest_map: str, dest_key: str = "__spawn__") -> None:
        ents = built[src_map]["map"]["entities"]
        dest_pos = positions[dest_map].get(dest_key) or positions[dest_map]["__spawn__"]
        for ent in ents:
            if ent.get("name") == ent_name and ent.get("type") == "teleporter":
                ent["target_map"] = dest_map
                ent["target_position"] = [dest_pos[0], dest_pos[1]]
                token = ent["token"]
                if token in built[src_map]["legend"]:
                    built[src_map]["legend"][token]["target_map"] = dest_map
                    built[src_map]["legend"][token]["target_position"] = [dest_pos[0], dest_pos[1]]
                print(f"  link {src_map}:{ent_name} -> {dest_map}{dest_pos}")

    # Prefer landing near the destination's exit teleporter back, else spawn
    set_tp("city_gate", "transition_to_streets", "city_streets", "__spawn__")
    set_tp("city_streets", "transition_to_gate", "city_gate", "__spawn__")
    set_tp("city_streets", "transition_to_manor", "investigator_manor", "exit_to_streets")
    set_tp("city_streets", "transition_to_prison", "prison", "exit_to_streets")
    set_tp("city_streets", "transition_to_cathedral", "cathedral", "exit_to_streets")
    set_tp("city_streets", "sewer_entrance", "sewers", "exit_to_streets")
    # Tavern is hand-authored (not regenerated); keep a fixed landing pad.
    for ent in built["city_streets"]["map"]["entities"]:
        if ent.get("name") == "tavern_entrance" and ent.get("type") == "teleporter":
            ent["target_map"] = "tavern"
            ent["target_position"] = [5, 8]
            token = ent["token"]
            if token in built["city_streets"]["legend"]:
                built["city_streets"]["legend"][token]["target_map"] = "tavern"
                built["city_streets"]["legend"][token]["target_position"] = [5, 8]
            print("  link city_streets:tavern_entrance -> tavern(5, 8)")
            break
    for ent in built["city_streets"]["map"]["entities"]:
        if ent.get("name") == "transition_to_docks" and ent.get("type") == "teleporter":
            ent["target_map"] = "docks"
            ent["target_position"] = [8, 8]
            token = ent["token"]
            if token in built["city_streets"]["legend"]:
                built["city_streets"]["legend"][token]["target_map"] = "docks"
                built["city_streets"]["legend"][token]["target_position"] = [8, 8]
            print("  link city_streets:transition_to_docks -> docks(8, 8)")
            break

    set_tp("investigator_manor", "exit_to_streets", "city_streets", "transition_to_manor")
    set_tp("sewers", "exit_to_streets", "city_streets", "sewer_entrance")
    set_tp("sewers", "deep_sewer", "cathedral", "hidden_passage")
    set_tp("prison", "exit_to_streets", "city_streets", "transition_to_prison")
    set_tp("prison", "secret_passage", "cathedral", "hidden_passage")
    set_tp("cathedral", "exit_to_streets", "city_streets", "transition_to_cathedral")
    set_tp("cathedral", "hidden_passage", "sewers", "deep_sewer")

    # Ensure altar and candle 5 don't share a tile
    cath_ents = built["cathedral"]["map"]["entities"]
    altar = next((e for e in cath_ents if e.get("name") == "ritual_altar"), None)
    candle5 = next((e for e in cath_ents if e.get("name") == "ritual_candle_5"), None)
    if altar and candle5 and altar.get("pos") == candle5.get("pos"):
        ax, ay = altar["pos"]
        candle5["pos"] = [min(ax + 1, built["cathedral"]["map"]["size"][0] - 2), ay]

    # Make bosses hostile-capable but passive until triggered; society members hostile
    for ent in cath_ents:
        if ent.get("sub_type") == "society_member":
            ov = ent.setdefault("overrides", {})
            ov["hostile"] = True
            ov["passive"] = False
        if ent.get("sub_type") in {"lady_ophelia", "kester_volo"}:
            ov = ent.setdefault("overrides", {})
            ov.setdefault("passive", True)
            ov.setdefault("dialog", True)

    # Write maps
    for map_id, props in built.items():
        path = MAPS / f"{map_id}.yml"
        path.write_text(yaml.safe_dump(props, sort_keys=False, allow_unicode=True), encoding="utf-8")
        print(f"Wrote {path}")

    # Fix locales if needed
    locale = CAMPAIGN / "locales" / "en.yml"
    if locale.is_file():
        raw = yaml.safe_load(locale.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "en" not in raw:
            locale.write_text(
                yaml.safe_dump({"en": raw}, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            print("Wrapped locales/en.yml under en:")

    # Re-render backgrounds
    print("Rendering map assets...")
    results = batch_render_missing_map_assets(
        CAMPAIGN,
        force=True,
        update_yaml=False,
        layers=("base", "objects", "entities"),
    )
    for r in results:
        if not r.skipped:
            print(f"  rendered {r.map_id} -> {r.output_path}")


if __name__ == "__main__":
    rebuild()
