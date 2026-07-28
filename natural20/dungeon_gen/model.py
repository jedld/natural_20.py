"""Shared dungeon grid / room model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

from natural20.dungeon_gen.knobs import RoomRole

FLOOR = "."
WALL = "#"
VOID = "_"
WATER = "w"
DOOR_H = "-"
DOOR_V = "|"


@dataclass
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def x2(self) -> int:
        return self.x + self.w - 1

    @property
    def y2(self) -> int:
        return self.y + self.h - 1

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    def intersects(self, other: "Rect", *, gap: int = 0) -> bool:
        return not (
            self.x2 + gap < other.x
            or other.x2 + gap < self.x
            or self.y2 + gap < other.y
            or other.y2 + gap < self.y
        )

    def inflate(self, amount: int) -> "Rect":
        return Rect(self.x - amount, self.y - amount, self.w + 2 * amount, self.h + 2 * amount)

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x <= self.x2 and self.y <= y <= self.y2

    def floor_cells(self) -> Iterator[tuple[int, int]]:
        for yy in range(self.y, self.y + self.h):
            for xx in range(self.x, self.x + self.w):
                yield xx, yy


@dataclass
class Room:
    id: int
    rect: Rect
    role: RoomRole = "combat"
    depth: int = 0
    tags: list[str] = field(default_factory=list)

    @property
    def center(self) -> tuple[int, int]:
        return self.rect.center


@dataclass
class Placement:
    kind: str
    x: int
    y: int
    token: str
    layer: str = "base_1"
    legend: dict[str, Any] = field(default_factory=dict)
    entity: dict[str, Any] | None = None
    objective_id: str | None = None


@dataclass
class DungeonGrid:
    width: int
    height: int
    cells: list[list[str]] = field(default_factory=list)
    rooms: list[Room] = field(default_factory=list)
    corridors: list[tuple[int, int]] = field(default_factory=list)
    """Edges as (room_id_a, room_id_b)."""
    placements: list[Placement] = field(default_factory=list)
    entrance_room_id: int | None = None
    exit_room_id: int | None = None
    critical_path: list[int] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.cells:
            self.cells = [[WALL for _ in range(self.height)] for _ in range(self.width)]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def get(self, x: int, y: int) -> str:
        return self.cells[x][y]

    def set(self, x: int, y: int, value: str) -> None:
        if self.in_bounds(x, y):
            self.cells[x][y] = value

    def carve_room(self, rect: Rect) -> None:
        for x, y in rect.floor_cells():
            if self.in_bounds(x, y):
                self.cells[x][y] = FLOOR

    def carve_h_corridor(self, x1: int, x2: int, y: int, width: int = 1) -> None:
        lo, hi = sorted((x1, x2))
        half = width // 2
        for x in range(lo, hi + 1):
            for dy in range(-half, half + 1):
                self.set(x, y + dy, FLOOR)

    def carve_v_corridor(self, y1: int, y2: int, x: int, width: int = 1) -> None:
        lo, hi = sorted((y1, y2))
        half = width // 2
        for y in range(lo, hi + 1):
            for dx in range(-half, half + 1):
                self.set(x + dx, y, FLOOR)

    def carve_l_corridor(self, a: tuple[int, int], b: tuple[int, int], width: int = 1, bend_horizontal_first: bool = True) -> None:
        ax, ay = a
        bx, by = b
        if bend_horizontal_first:
            self.carve_h_corridor(ax, bx, ay, width)
            self.carve_v_corridor(ay, by, bx, width)
        else:
            self.carve_v_corridor(ay, by, ax, width)
            self.carve_h_corridor(ax, bx, by, width)

    def room_by_id(self, room_id: int) -> Room | None:
        for room in self.rooms:
            if room.id == room_id:
                return room
        return None

    def floor_positions(self) -> list[tuple[int, int]]:
        return [
            (x, y)
            for x in range(self.width)
            for y in range(self.height)
            if self.cells[x][y] in {FLOOR, WATER, DOOR_H, DOOR_V}
        ]

    def is_walkable(self, x: int, y: int, *, doors_passable: bool = True) -> bool:
        if not self.in_bounds(x, y):
            return False
        cell = self.cells[x][y]
        if cell in {FLOOR, WATER}:
            return True
        if doors_passable and cell in {DOOR_H, DOOR_V}:
            return True
        return False
