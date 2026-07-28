"""Room semantics and content placement for mission objectives."""

from __future__ import annotations

import random
from collections import defaultdict, deque
from typing import Any

from natural20.dungeon_gen.knobs import GeneratorKnobs, ObjectiveSpec, RoomRole
from natural20.dungeon_gen.model import (
    DOOR_H,
    DOOR_V,
    FLOOR,
    WALL,
    WATER,
    DungeonGrid,
    Placement,
    Room,
)


def assign_room_semantics(grid: DungeonGrid, knobs: GeneratorKnobs, rng: random.Random) -> None:
    if not grid.rooms:
        return
    # Entrance = room closest to map origin-ish (or leftmost)
    entrance = min(grid.rooms, key=lambda r: r.center[0] + r.center[1] * 0.3)
    grid.entrance_room_id = entrance.id

    adjacency = _adjacency(grid)
    depths = _bfs_depths(entrance.id, adjacency)
    for room in grid.rooms:
        room.depth = depths.get(room.id, 0)

    max_depth = max((r.depth for r in grid.rooms), default=0)
    exit_room = max(grid.rooms, key=lambda r: (r.depth, r.center[0] + r.center[1]))
    grid.exit_room_id = exit_room.id
    grid.critical_path = _critical_path(entrance.id, exit_room.id, adjacency)

    for room in grid.rooms:
        room.role = _role_for_room(room, max_depth, exit_room.id, knobs, rng)


def _adjacency(grid: DungeonGrid) -> dict[int, list[int]]:
    adj: dict[int, list[int]] = defaultdict(list)
    for a, b in grid.corridors:
        adj[a].append(b)
        adj[b].append(a)
    # Ensure isolated rooms still appear
    for room in grid.rooms:
        adj.setdefault(room.id, [])
    return adj


def _bfs_depths(start: int, adjacency: dict[int, list[int]]) -> dict[int, int]:
    depths = {start: 0}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for nxt in adjacency.get(node, []):
            if nxt in depths:
                continue
            depths[nxt] = depths[node] + 1
            queue.append(nxt)
    return depths


def _critical_path(start: int, end: int, adjacency: dict[int, list[int]]) -> list[int]:
    parent: dict[int, int | None] = {start: None}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node == end:
            break
        for nxt in adjacency.get(node, []):
            if nxt in parent:
                continue
            parent[nxt] = node
            queue.append(nxt)
    if end not in parent:
        return [start]
    path = []
    cur: int | None = end
    while cur is not None:
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path


def _role_for_room(
    room: Room,
    max_depth: int,
    exit_id: int,
    knobs: GeneratorKnobs,
    rng: random.Random,
) -> RoomRole:
    if room.depth == 0:
        return "entrance"
    if room.id == exit_id:
        return "boss" if knobs.boss_types else "exit"
    if max_depth <= 0:
        return "combat"
    ratio = room.depth / max_depth
    if ratio >= 0.85 and room.id == exit_id:
        return "boss"
    if ratio >= 0.7 and rng.random() < 0.45:
        return "elite"
    if 0.4 <= ratio <= 0.75 and rng.random() < 0.25:
        return "treasure"
    if rng.random() < 0.12:
        return "shrine"
    if room.depth == 1 and rng.random() < 0.3:
        return "hub"
    return "combat"


def place_content(grid: DungeonGrid, knobs: GeneratorKnobs, rng: random.Random) -> None:
    """Place doors, traps, chests, enemies, lights, water, and objectives."""
    _maybe_add_water(grid, knobs, rng)
    _place_doors(grid, knobs, rng)
    _place_density_features(grid, knobs, rng)
    _place_objectives(grid, knobs, rng)
    if knobs.place_entrance_spawn:
        _place_spawn(grid, knobs)
    if knobs.place_exit_teleporter:
        _place_exit(grid, knobs)


def _room_floor_tiles(grid: DungeonGrid, room: Room) -> list[tuple[int, int]]:
    tiles = []
    for x, y in room.rect.floor_cells():
        if grid.in_bounds(x, y) and grid.cells[x][y] == FLOOR:
            # Prefer interior cells (not on rect edge touching corridors as much)
            tiles.append((x, y))
    return tiles


def _free_tile(
    grid: DungeonGrid,
    room: Room,
    rng: random.Random,
    *,
    occupied: set[tuple[int, int]],
) -> tuple[int, int] | None:
    tiles = [t for t in _room_floor_tiles(grid, room) if t not in occupied]
    if not tiles:
        return None
    # Prefer not the exact center if already taken; shuffle
    rng.shuffle(tiles)
    return tiles[0]


def _maybe_add_water(grid: DungeonGrid, knobs: GeneratorKnobs, rng: random.Random) -> None:
    if knobs.water_chance <= 0:
        return
    floors = grid.floor_positions()
    for x, y in floors:
        if rng.random() > knobs.water_chance * 0.08:
            continue
        # Prefer near walls / edges of open space
        walls = sum(
            1
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            if not grid.in_bounds(x + dx, y + dy) or grid.cells[x + dx][y + dy] == WALL
        )
        if walls >= 1 and rng.random() < 0.6:
            grid.cells[x][y] = WATER


def _place_doors(grid: DungeonGrid, knobs: GeneratorKnobs, rng: random.Random) -> None:
    if knobs.door_chance <= 0:
        return
    for room in grid.rooms:
        if room.role == "entrance":
            continue
        for x, y in _room_floor_tiles(grid, room):
            # Door candidates: floor with exactly one orthogonal wall neighbor pair forming a choke
            for dx, dy, door in ((1, 0, DOOR_V), (-1, 0, DOOR_V), (0, 1, DOOR_H), (0, -1, DOOR_H)):
                nx, ny = x + dx, y + dy
                if not grid.in_bounds(nx, ny):
                    continue
                if grid.cells[nx][ny] != FLOOR:
                    continue
                # Outside room rect → corridor junction
                if room.rect.contains(nx, ny):
                    continue
                if rng.random() > knobs.door_chance:
                    continue
                # Place door on the boundary cell
                grid.cells[x][y] = door
                token = "D"
                grid.placements.append(
                    Placement(
                        kind="door",
                        x=x,
                        y=y,
                        token=token,
                        layer="base",
                        legend={
                            "name": "door",
                            "type": "wooden_door",
                            "state": "closed",
                        },
                    )
                )
                break


def _place_density_features(grid: DungeonGrid, knobs: GeneratorKnobs, rng: random.Random) -> None:
    occupied = {(p.x, p.y) for p in grid.placements}
    enemy_token_i = 0
    trap_i = 0
    chest_i = 0

    for room in grid.rooms:
        if room.role == "entrance":
            continue
        tiles = _room_floor_tiles(grid, room)
        if not tiles:
            continue

        # Enemies
        enemy_count = 0
        if room.role == "boss":
            enemy_count = 1
            roster = knobs.boss_types or knobs.elite_types or knobs.enemy_types
        elif room.role == "elite":
            enemy_count = 1 + (1 if rng.random() < knobs.enemy_density else 0)
            roster = knobs.elite_types or knobs.enemy_types
        elif room.role in {"combat", "hub"}:
            enemy_count = int(len(tiles) * knobs.enemy_density * 0.08) + (
                1 if rng.random() < knobs.enemy_density else 0
            )
            roster = knobs.enemy_types
        else:
            roster = knobs.enemy_types
            enemy_count = 1 if rng.random() < knobs.enemy_density * 0.4 else 0

        for _ in range(max(0, enemy_count)):
            if not roster:
                break
            pos = _free_tile(grid, room, rng, occupied=occupied)
            if not pos:
                break
            occupied.add(pos)
            npc_type = rng.choice(roster)
            token = f"E{enemy_token_i}"
            enemy_token_i += 1
            grid.placements.append(
                Placement(
                    kind="enemy",
                    x=pos[0],
                    y=pos[1],
                    token=token,
                    layer="meta",
                    legend={
                        "name": "_auto_",
                        "type": "npc",
                        "sub_type": npc_type,
                        "group": knobs.enemy_group,
                    },
                    entity={
                        "token": token,
                        "pos": [pos[0], pos[1]],
                        "name": f"{npc_type}_{enemy_token_i}",
                        "type": "npc",
                        "sub_type": npc_type,
                        "group": knobs.enemy_group,
                        "overrides": {"hostile": True, "passive": False},
                    },
                )
            )

        # Traps
        if room.role in {"combat", "elite", "boss", "treasure"} and rng.random() < knobs.trap_density:
            pos = _free_tile(grid, room, rng, occupied=occupied)
            if pos:
                occupied.add(pos)
                token = f"T{trap_i}"
                trap_i += 1
                grid.placements.append(
                    Placement(
                        kind="trap",
                        x=pos[0],
                        y=pos[1],
                        token=token,
                        layer="base_1",
                        legend={"name": "pit trap", "type": "pit_trap"},
                    )
                )

        # Chests
        chest_roll = knobs.chest_density
        if room.role == "treasure":
            chest_roll = max(chest_roll, 0.85)
        if room.role == "boss":
            chest_roll = max(chest_roll, 0.6)
        if rng.random() < chest_roll:
            pos = _free_tile(grid, room, rng, occupied=occupied)
            if pos:
                occupied.add(pos)
                token = f"C{chest_i}"
                chest_i += 1
                grid.placements.append(
                    Placement(
                        kind="chest",
                        x=pos[0],
                        y=pos[1],
                        token=token,
                        layer="base_1",
                        legend={
                            "name": "chest",
                            "type": "chest",
                            "inventory": [
                                {"type": "healing_potion", "qty": 1},
                                {"type": "arrows", "qty": 10},
                            ],
                        },
                    )
                )

        # Lights
        if rng.random() < knobs.light_density:
            pos = _free_tile(grid, room, rng, occupied=occupied)
            if pos:
                occupied.add(pos)
                token = f"L{room.id}"
                grid.placements.append(
                    Placement(
                        kind="light",
                        x=pos[0],
                        y=pos[1],
                        token=token,
                        layer="base_2",
                        legend={"name": "campfire", "type": "campfire"},
                    )
                )


def _select_room_for_objective(
    grid: DungeonGrid,
    spec: ObjectiveSpec,
    rng: random.Random,
) -> Room | None:
    if not grid.rooms:
        return None
    max_depth = max((r.depth for r in grid.rooms), default=0) or 1
    candidates = list(grid.rooms)
    if spec.room_role:
        role_matches = [r for r in candidates if r.role == spec.room_role]
        if role_matches:
            candidates = role_matches
    if spec.depth != "any":
        filtered = []
        for room in candidates:
            ratio = room.depth / max_depth
            if spec.depth == "near" and ratio <= 0.34:
                filtered.append(room)
            elif spec.depth == "mid" and 0.34 < ratio <= 0.7:
                filtered.append(room)
            elif spec.depth == "far" and ratio > 0.7:
                filtered.append(room)
        if filtered:
            candidates = filtered
    return rng.choice(candidates) if candidates else None


def _place_objectives(grid: DungeonGrid, knobs: GeneratorKnobs, rng: random.Random) -> None:
    occupied = {(p.x, p.y) for p in grid.placements}
    for spec in knobs.objectives:
        room = _select_room_for_objective(grid, spec, rng)
        if room is None:
            if spec.required:
                grid.meta.setdefault("placement_errors", []).append(
                    f"Could not place required objective {spec.id}"
                )
            continue
        if spec.room_role == "objective" or spec.kind in {"interactive_object", "altar", "symbol", "note"}:
            room.role = room.role if room.role != "combat" else "objective"
            room.tags.append(spec.id)

        pos = _free_tile(grid, room, rng, occupied=occupied)
        if not pos:
            if spec.required:
                grid.meta.setdefault("placement_errors", []).append(
                    f"No free tile for objective {spec.id}"
                )
            continue
        occupied.add(pos)
        token = f"O_{spec.id}"[:12]
        placement = _placement_from_spec(spec, token, pos, knobs)
        grid.placements.append(placement)


def _placement_from_spec(
    spec: ObjectiveSpec,
    token: str,
    pos: tuple[int, int],
    knobs: GeneratorKnobs,
) -> Placement:
    x, y = pos
    kind = spec.kind
    if kind == "spawn":
        return Placement(
            kind="spawn",
            x=x,
            y=y,
            token=token,
            layer="meta",
            legend={"type": "spawn_point", "name": spec.label or "spawn"},
            objective_id=spec.id,
            entity=None,
        )
    if kind in {"npc", "enemy"}:
        npc_type = spec.npc_type or (knobs.enemy_types[0] if knobs.enemy_types else "goblin")
        return Placement(
            kind=kind,
            x=x,
            y=y,
            token=token,
            layer="meta",
            legend={
                "name": spec.label or "_auto_",
                "type": "npc",
                "sub_type": npc_type,
                "group": spec.group,
            },
            entity={
                "token": token,
                "pos": [x, y],
                "name": spec.id,
                "type": "npc",
                "sub_type": npc_type,
                "group": spec.group,
                "overrides": {
                    "label": spec.label or spec.id,
                    "hostile": spec.hostile or kind == "enemy",
                    "passive": not (spec.hostile or kind == "enemy"),
                    "dialog": spec.dialog,
                },
            },
            objective_id=spec.id,
        )
    if kind == "teleporter":
        legend: dict[str, Any] = {
            "name": spec.label or "teleporter",
            "type": "teleporter",
            "target_position": [0, 0],
        }
        if spec.target_map:
            legend["target_map"] = spec.target_map
        return Placement(
            kind="teleporter",
            x=x,
            y=y,
            token=token,
            layer="base_1",
            legend=legend,
            entity={
                "token": token,
                "pos": [x, y],
                "layer": "object",
                "name": spec.id,
                "type": "teleporter",
                "target_map": spec.target_map,
                "target_position": [0, 0],
                "overrides": {"label": spec.label or spec.id},
            },
            objective_id=spec.id,
        )
    if kind == "chest":
        return Placement(
            kind="chest",
            x=x,
            y=y,
            token=token,
            layer="base_1",
            legend={
                "name": spec.label or "chest",
                "type": "chest",
                "inventory": spec.inventory
                or [{"type": "healing_potion", "qty": 1}],
            },
            objective_id=spec.id,
        )
    if kind == "trap":
        return Placement(
            kind="trap",
            x=x,
            y=y,
            token=token,
            layer="base_1",
            legend={"name": spec.label or "pit trap", "type": "pit_trap"},
            objective_id=spec.id,
        )

    type_map = {
        "altar": "interactive_object",
        "note": "note",
        "symbol": "interactive_object",
        "interactive_object": "interactive_object",
    }
    obj_type = type_map.get(kind, "interactive_object")
    legend = {
        "name": spec.label or spec.id,
        "type": obj_type,
    }
    if spec.notes:
        legend["notes"] = [{"note": n} for n in spec.notes]
    return Placement(
        kind=kind,
        x=x,
        y=y,
        token=token,
        layer="base_1",
        legend=legend,
        entity={
            "token": token,
            "pos": [x, y],
            "layer": "object",
            "name": spec.id,
            "type": obj_type,
            "overrides": {
                "label": spec.label or spec.id,
                "backstory": "\n".join(spec.notes) if spec.notes else "",
            },
        },
        objective_id=spec.id,
    )


def _place_spawn(grid: DungeonGrid, knobs: GeneratorKnobs) -> None:
    room = grid.room_by_id(grid.entrance_room_id) if grid.entrance_room_id is not None else None
    if not room:
        return
    cx, cy = room.center
    if not grid.is_walkable(cx, cy):
        tiles = _room_floor_tiles(grid, room)
        if not tiles:
            return
        cx, cy = tiles[0]
    grid.placements.append(
        Placement(
            kind="spawn",
            x=cx,
            y=cy,
            token="SP",
            layer="meta",
            legend={"type": "spawn_point", "name": "player_spawn"},
        )
    )
    grid.meta["player_spawn_points"] = [{"position": [cx, cy], "group": knobs.player_group}]


def _place_exit(grid: DungeonGrid, knobs: GeneratorKnobs) -> None:
    room = grid.room_by_id(grid.exit_room_id) if grid.exit_room_id is not None else None
    if not room:
        return
    tiles = _room_floor_tiles(grid, room)
    if not tiles:
        return
    x, y = tiles[-1]
    target_pos = knobs.exit_target_position or [0, 0]
    legend: dict[str, Any] = {
        "name": "exit",
        "type": "teleporter",
        "target_position": target_pos,
    }
    if knobs.exit_target_map:
        legend["target_map"] = knobs.exit_target_map
    grid.placements.append(
        Placement(
            kind="teleporter",
            x=x,
            y=y,
            token="EX",
            layer="base_1",
            legend=legend,
            entity={
                "token": "EX",
                "pos": [x, y],
                "layer": "object",
                "name": "exit",
                "type": "teleporter",
                "target_map": knobs.exit_target_map,
                "target_position": target_pos,
                "overrides": {"label": "Exit"},
            },
        )
    )
