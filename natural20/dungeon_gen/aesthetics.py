"""Aesthetic scoring heuristics for procedural dungeons."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from natural20.dungeon_gen.model import WALL, DungeonGrid
from natural20.dungeon_gen.topology import find_spawn, flood_reachable, shortest_path_length


@dataclass
class AestheticsReport:
    score: float
    """Aggregate 0–1 score (higher is better)."""
    metrics: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "metrics": {k: round(v, 4) for k, v in self.metrics.items()},
            "notes": self.notes,
        }


def analyze_aesthetics(grid: DungeonGrid) -> AestheticsReport:
    """Score layout quality using industry-inspired heuristics."""
    report = AestheticsReport(score=0.0)
    total = grid.width * grid.height
    floors = grid.floor_positions()
    floor_n = len(floors)
    if total == 0 or floor_n == 0:
        report.notes.append("Empty map")
        return report

    floor_ratio = floor_n / total
    floor_score = _peak(floor_ratio, low=0.18, high=0.62, ideal=0.38)

    aspect_penalties = []
    for room in grid.rooms:
        aspect = max(room.rect.w, room.rect.h) / max(1, min(room.rect.w, room.rect.h))
        aspect_penalties.append(min(1.0, abs(aspect - 1.4) / 3.0))
    aspect_score = 1.0 - (sum(aspect_penalties) / len(aspect_penalties) if aspect_penalties else 0.3)

    room_n = max(1, len(grid.rooms))
    edge_n = len(grid.corridors)
    loop_extra = max(0, edge_n - (room_n - 1))
    loop_score = _peak(loop_extra / room_n, low=0.0, high=0.7, ideal=0.25)

    path_len = len(grid.critical_path)
    path_score = _peak(path_len / room_n, low=0.25, high=1.0, ideal=0.55)

    dead_ends = 0
    for x, y in floors:
        walls = 0
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if not grid.in_bounds(nx, ny) or grid.cells[nx][ny] == WALL:
                walls += 1
        if walls >= 3:
            dead_ends += 1
    dead_end_ratio = dead_ends / floor_n
    dead_end_score = 1.0 - min(1.0, dead_end_ratio / 0.25)

    feature_n = len(grid.placements)
    feature_score = _peak(feature_n / room_n, low=0.5, high=8.0, ideal=3.0)

    span_score = 0.5
    exit_room = grid.room_by_id(grid.exit_room_id) if grid.exit_room_id is not None else None
    entrance_room = (
        grid.room_by_id(grid.entrance_room_id) if grid.entrance_room_id is not None else None
    )
    if entrance_room and exit_room:
        dist = abs(entrance_room.center[0] - exit_room.center[0]) + abs(
            entrance_room.center[1] - exit_room.center[1]
        )
        span_score = _peak(dist / (grid.width + grid.height), low=0.1, high=0.8, ideal=0.4)

    traverse_score = 0.0
    spawn = find_spawn(grid)
    if spawn and exit_room:
        length = shortest_path_length(grid, spawn, exit_room.center)
        if length is not None:
            traverse_score = _peak(length / max(floor_n, 1), low=0.02, high=0.35, ideal=0.12)
        else:
            report.notes.append("No tile path from spawn to exit room")
    elif spawn:
        reachable = flood_reachable(grid, spawn)
        traverse_score = min(1.0, len(reachable) / max(floor_n, 1))

    weights = {
        "floor_ratio": 0.15,
        "aspect": 0.1,
        "loops": 0.15,
        "critical_path": 0.15,
        "dead_ends": 0.1,
        "features": 0.1,
        "span": 0.1,
        "traverse": 0.15,
    }
    metrics = {
        "floor_ratio": floor_score,
        "aspect": aspect_score,
        "loops": loop_score,
        "critical_path": path_score,
        "dead_ends": dead_end_score,
        "features": feature_score,
        "span": span_score,
        "traverse": traverse_score,
    }
    report.score = max(0.0, min(1.0, sum(metrics[k] * weights[k] for k in weights)))
    report.metrics = metrics

    if floor_ratio < 0.15:
        report.notes.append("Very closed-in (low floor ratio)")
    if floor_ratio > 0.65:
        report.notes.append("Very open (high floor ratio)")
    if loop_extra == 0 and room_n > 3:
        report.notes.append("No corridor loops — may feel linear")
    if dead_end_ratio > 0.2:
        report.notes.append("Many dead-end tiles")
    return report


def _peak(value: float, *, low: float, high: float, ideal: float) -> float:
    if value < low:
        return max(0.0, 1.0 - (low - value) / max(low, 0.01))
    if value > high:
        return max(0.0, 1.0 - (value - high) / max(1.0 - high, 0.01))
    if value == ideal:
        return 1.0
    if value < ideal:
        return (value - low) / max(ideal - low, 1e-6)
    return (high - value) / max(high - ideal, 1e-6)
