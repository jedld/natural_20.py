"""Traversability analysis for generated dungeons."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from natural20.dungeon_gen.model import FLOOR, WATER, DungeonGrid


@dataclass
class TraversabilityReport:
    ok: bool
    reachable_floor: int = 0
    total_floor: int = 0
    reachable_ratio: float = 0.0
    unreachable_floors: list[tuple[int, int]] = field(default_factory=list)
    unreachable_objectives: list[str] = field(default_factory=list)
    spawn: tuple[int, int] | None = None
    critical_path_rooms: list[int] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reachable_floor": self.reachable_floor,
            "total_floor": self.total_floor,
            "reachable_ratio": round(self.reachable_ratio, 4),
            "unreachable_floors_sample": self.unreachable_floors[:20],
            "unreachable_objectives": self.unreachable_objectives,
            "spawn": list(self.spawn) if self.spawn else None,
            "critical_path_rooms": self.critical_path_rooms,
            "messages": self.messages,
        }


def find_spawn(grid: DungeonGrid) -> tuple[int, int] | None:
    for placement in grid.placements:
        if placement.kind == "spawn":
            return placement.x, placement.y
    if grid.entrance_room_id is not None:
        room = grid.room_by_id(grid.entrance_room_id)
        if room:
            cx, cy = room.center
            if grid.is_walkable(cx, cy):
                return cx, cy
    floors = grid.floor_positions()
    return floors[0] if floors else None


def flood_reachable(
    grid: DungeonGrid,
    start: tuple[int, int],
    *,
    doors_passable: bool = True,
) -> set[tuple[int, int]]:
    if not grid.is_walkable(*start, doors_passable=doors_passable):
        return set()
    seen = {start}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if (nx, ny) in seen:
                continue
            if not grid.is_walkable(nx, ny, doors_passable=doors_passable):
                continue
            seen.add((nx, ny))
            queue.append((nx, ny))
    return seen


def analyze_traversability(
    grid: DungeonGrid,
    *,
    min_reachable_ratio: float = 0.92,
    doors_passable: bool = True,
) -> TraversabilityReport:
    report = TraversabilityReport(ok=True)
    report.total_floor = len(grid.floor_positions())
    spawn = find_spawn(grid)
    report.spawn = spawn
    report.critical_path_rooms = list(grid.critical_path)

    if not spawn:
        report.ok = False
        report.messages.append("No spawn / walkable start position")
        return report

    reachable = flood_reachable(grid, spawn, doors_passable=doors_passable)
    report.reachable_floor = len(reachable)
    report.reachable_ratio = (
        report.reachable_floor / report.total_floor if report.total_floor else 0.0
    )
    report.unreachable_floors = [p for p in grid.floor_positions() if p not in reachable]

    if report.reachable_ratio < min_reachable_ratio:
        report.ok = False
        report.messages.append(
            f"Reachable floor ratio {report.reachable_ratio:.2%} "
            f"< required {min_reachable_ratio:.2%}"
        )

    for placement in grid.placements:
        if placement.objective_id and (placement.x, placement.y) not in reachable:
            neighbors = [
                (placement.x + dx, placement.y + dy)
                for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))
            ]
            if not any(n in reachable for n in neighbors):
                report.unreachable_objectives.append(placement.objective_id)
                report.ok = False

    if report.unreachable_objectives:
        report.messages.append(
            "Unreachable objectives: " + ", ".join(report.unreachable_objectives)
        )

    if len(grid.critical_path) < 2 and len(grid.rooms) > 2:
        report.messages.append("Critical path is very short relative to room count")

    return report


def shortest_path_length(
    grid: DungeonGrid,
    start: tuple[int, int],
    goal: tuple[int, int],
    *,
    doors_passable: bool = True,
) -> int | None:
    if start == goal:
        return 0
    seen = {start}
    queue = deque([(start[0], start[1], 0)])
    while queue:
        x, y, dist = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if (nx, ny) in seen:
                continue
            if not grid.is_walkable(nx, ny, doors_passable=doors_passable):
                continue
            if (nx, ny) == goal:
                return dist + 1
            seen.add((nx, ny))
            queue.append((nx, ny, dist + 1))
    return None
