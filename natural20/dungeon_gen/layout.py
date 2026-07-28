"""Dungeon layout algorithms: BSP, scatter+MST, cellular automata."""

from __future__ import annotations

import random
from dataclasses import dataclass

from natural20.dungeon_gen.knobs import GeneratorKnobs
from natural20.dungeon_gen.model import FLOOR, WALL, DungeonGrid, Rect, Room


@dataclass
class _BSPNode:
    rect: Rect
    left: "_BSPNode | None" = None
    right: "_BSPNode | None" = None
    room: Room | None = None

    @property
    def leaf(self) -> bool:
        return self.left is None and self.right is None


def generate_layout(knobs: GeneratorKnobs, rng: random.Random) -> DungeonGrid:
    algo = knobs.algorithm
    if algo == "cellular":
        return generate_cellular(knobs, rng)
    if algo == "rooms_graph":
        return generate_rooms_graph(knobs, rng)
    if algo == "hybrid":
        grid = generate_bsp(knobs, rng)
        if rng.random() < knobs.hybrid_cave_wing_chance and grid.rooms:
            _grow_cave_wing(grid, knobs, rng)
        return grid
    return generate_bsp(knobs, rng)


def generate_bsp(knobs: GeneratorKnobs, rng: random.Random) -> DungeonGrid:
    """Binary Space Partitioning — classic Rogue / many roguelikes."""
    grid = DungeonGrid(knobs.width, knobs.height)
    root = _BSPNode(Rect(1, 1, knobs.width - 2, knobs.height - 2))
    leaves: list[_BSPNode] = []
    _split_bsp(root, knobs, rng, leaves, depth=0)

    rooms: list[Room] = []
    for index, leaf in enumerate(leaves):
        room_rect = _room_in_partition(leaf.rect, knobs, rng)
        if room_rect is None:
            continue
        room = Room(id=len(rooms), rect=room_rect)
        leaf.room = room
        rooms.append(room)
        grid.carve_room(room_rect)

    if len(rooms) < 2:
        # Fallback: one central room
        cx, cy = knobs.width // 2, knobs.height // 2
        rect = Rect(cx - 4, cy - 3, 9, 7)
        room = Room(id=0, rect=rect)
        rooms = [room]
        grid.carve_room(rect)

    grid.rooms = rooms
    edges = _connect_bsp(root, knobs, rng, grid)
    grid.corridors = edges
    return grid


def _split_bsp(
    node: _BSPNode,
    knobs: GeneratorKnobs,
    rng: random.Random,
    leaves: list[_BSPNode],
    depth: int,
) -> None:
    min_size = knobs.room_min_size + 2
    can_split_h = node.rect.h >= min_size * 2
    can_split_v = node.rect.w >= min_size * 2
    target_leaves = knobs.room_count
    if depth > 8 or (not can_split_h and not can_split_v) or len(leaves) >= target_leaves:
        leaves.append(node)
        return
    # Prefer splitting until we approach room_count
    if len(leaves) + _estimate_leaves(node) >= target_leaves and depth > 2 and rng.random() < 0.4:
        leaves.append(node)
        return

    horizontal = can_split_h and (not can_split_v or rng.random() < 0.5)
    if horizontal:
        split = rng.randint(min_size, node.rect.h - min_size)
        node.left = _BSPNode(Rect(node.rect.x, node.rect.y, node.rect.w, split))
        node.right = _BSPNode(
            Rect(node.rect.x, node.rect.y + split, node.rect.w, node.rect.h - split)
        )
    else:
        if not can_split_v:
            leaves.append(node)
            return
        split = rng.randint(min_size, node.rect.w - min_size)
        node.left = _BSPNode(Rect(node.rect.x, node.rect.y, split, node.rect.h))
        node.right = _BSPNode(
            Rect(node.rect.x + split, node.rect.y, node.rect.w - split, node.rect.h)
        )
    _split_bsp(node.left, knobs, rng, leaves, depth + 1)
    _split_bsp(node.right, knobs, rng, leaves, depth + 1)


def _estimate_leaves(node: _BSPNode) -> int:
    if node.leaf:
        return 1
    return _estimate_leaves(node.left) + _estimate_leaves(node.right)  # type: ignore[arg-type]


def _room_in_partition(partition: Rect, knobs: GeneratorKnobs, rng: random.Random) -> Rect | None:
    max_w = min(knobs.room_max_size, partition.w - 2)
    max_h = min(knobs.room_max_size, partition.h - 2)
    min_w = min(knobs.room_min_size, max_w)
    min_h = min(knobs.room_min_size, max_h)
    if max_w < min_w or max_h < min_h:
        return None
    w = rng.randint(min_w, max_w)
    h = rng.randint(min_h, max_h)
    x = rng.randint(partition.x + 1, partition.x2 - w)
    y = rng.randint(partition.y + 1, partition.y2 - h)
    return Rect(x, y, w, h)


def _connect_bsp(
    node: _BSPNode,
    knobs: GeneratorKnobs,
    rng: random.Random,
    grid: DungeonGrid,
) -> list[tuple[int, int]]:
    edges: list[tuple[int, int]] = []

    def rooms_in(n: _BSPNode) -> list[Room]:
        if n.room:
            return [n.room]
        result: list[Room] = []
        if n.left:
            result.extend(rooms_in(n.left))
        if n.right:
            result.extend(rooms_in(n.right))
        return result

    def connect(n: _BSPNode) -> None:
        if n.leaf:
            return
        assert n.left and n.right
        connect(n.left)
        connect(n.right)
        left_rooms = rooms_in(n.left)
        right_rooms = rooms_in(n.right)
        if not left_rooms or not right_rooms:
            return
        a = rng.choice(left_rooms)
        b = rng.choice(right_rooms)
        bend = rng.random() < 0.5
        grid.carve_l_corridor(a.center, b.center, knobs.corridor_width, bend)
        edges.append((a.id, b.id))

    connect(node)

    # Optional extra loops based on loop_ratio / inverse linearity
    extra_budget = int(len(grid.rooms) * knobs.loop_ratio * (1.0 - 0.5 * knobs.linearity))
    if extra_budget > 0 and len(grid.rooms) > 2:
        for _ in range(extra_budget):
            a, b = rng.sample(grid.rooms, 2)
            if (a.id, b.id) in edges or (b.id, a.id) in edges:
                continue
            grid.carve_l_corridor(a.center, b.center, knobs.corridor_width, rng.random() < 0.5)
            edges.append((a.id, b.id))
    return edges


def generate_rooms_graph(knobs: GeneratorKnobs, rng: random.Random) -> DungeonGrid:
    """Scatter rooms, separate overlaps, MST connect, reintroduce loops.

    Inspired by Binding of Isaac / modern graph-dungeon pipelines
    (Delaunay → MST → loops). We approximate Delaunay with k-nearest
    candidate edges for simplicity and speed.
    """
    grid = DungeonGrid(knobs.width, knobs.height)
    rooms: list[Room] = []
    attempts = 0
    while len(rooms) < knobs.room_count and attempts < knobs.room_count * 40:
        attempts += 1
        w = rng.randint(knobs.room_min_size, knobs.room_max_size)
        h = rng.randint(knobs.room_min_size, knobs.room_max_size)
        x = rng.randint(knobs.padding + 1, max(knobs.padding + 1, knobs.width - w - knobs.padding - 1))
        y = rng.randint(knobs.padding + 1, max(knobs.padding + 1, knobs.height - h - knobs.padding - 1))
        rect = Rect(x, y, w, h)
        if any(rect.intersects(r.rect, gap=1) for r in rooms):
            continue
        room = Room(id=len(rooms), rect=rect)
        rooms.append(room)

    # Separation pass for residual overlaps
    for _ in range(20):
        moved = False
        for i, room in enumerate(rooms):
            for other in rooms[i + 1 :]:
                if not room.rect.intersects(other.rect, gap=1):
                    continue
                dx = other.rect.center[0] - room.rect.center[0]
                dy = other.rect.center[1] - room.rect.center[1]
                if dx == 0 and dy == 0:
                    dx = 1
                if abs(dx) >= abs(dy):
                    other.rect.x = min(max(1, other.rect.x + (1 if dx > 0 else -1)), knobs.width - other.rect.w - 1)
                else:
                    other.rect.y = min(max(1, other.rect.y + (1 if dy > 0 else -1)), knobs.height - other.rect.h - 1)
                moved = True
        if not moved:
            break

    for room in rooms:
        # Clamp after separation
        room.rect.x = min(max(1, room.rect.x), knobs.width - room.rect.w - 1)
        room.rect.y = min(max(1, room.rect.y), knobs.height - room.rect.h - 1)
        grid.carve_room(room.rect)

    grid.rooms = rooms
    if len(rooms) < 2:
        return grid

    # Candidate edges: k-nearest neighbors (Delaunay approximation)
    candidates: list[tuple[float, int, int]] = []
    for i, a in enumerate(rooms):
        dists = []
        for j, b in enumerate(rooms):
            if i >= j:
                continue
            ax, ay = a.center
            bx, by = b.center
            dist = (ax - bx) ** 2 + (ay - by) ** 2
            dists.append((dist, i, j))
        dists.sort()
        candidates.extend(dists[:3])
    candidates = sorted(set(candidates))

    # Kruskal MST
    parent = list(range(len(rooms)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    mst: list[tuple[int, int]] = []
    remaining: list[tuple[float, int, int]] = []
    for dist, i, j in sorted(candidates):
        ri, rj = find(i), find(j)
        if ri == rj:
            remaining.append((dist, i, j))
            continue
        parent[ri] = rj
        mst.append((i, j))

    edges = list(mst)
    loop_count = int(len(remaining) * knobs.loop_ratio * (1.0 - 0.6 * knobs.linearity))
    for _, i, j in remaining[:loop_count]:
        edges.append((i, j))

    for i, j in edges:
        a, b = rooms[i], rooms[j]
        grid.carve_l_corridor(a.center, b.center, knobs.corridor_width, rng.random() < 0.5)

    grid.corridors = edges
    return grid


def generate_cellular(knobs: GeneratorKnobs, rng: random.Random) -> DungeonGrid:
    """Cellular automata caves — Dwarf Fortress / Spelunky style."""
    grid = DungeonGrid(knobs.width, knobs.height)
    for x in range(knobs.width):
        for y in range(knobs.height):
            if x == 0 or y == 0 or x == knobs.width - 1 or y == knobs.height - 1:
                grid.cells[x][y] = WALL
            else:
                grid.cells[x][y] = WALL if rng.random() < knobs.cave_fill_chance else FLOOR

    for _ in range(knobs.cave_iterations):
        grid.cells = _cave_step(grid, knobs)

    # Keep largest connected floor component
    components = _floor_components(grid)
    if not components:
        return grid
    components.sort(key=len, reverse=True)
    keep = set(components[0])
    for x in range(grid.width):
        for y in range(grid.height):
            if grid.cells[x][y] == FLOOR and (x, y) not in keep:
                grid.cells[x][y] = WALL

    # Approximate rooms as axis-aligned bounding boxes of floor clusters
    # via a coarse grid sample of open areas
    rooms = _rooms_from_open_space(grid, knobs, rng)
    grid.rooms = rooms
    if rooms:
        # Connect room centers if not already linked through open space
        for i in range(len(rooms) - 1):
            grid.carve_l_corridor(rooms[i].center, rooms[i + 1].center, knobs.corridor_width, True)
            grid.corridors.append((rooms[i].id, rooms[i + 1].id))
    return grid


def _cave_step(grid: DungeonGrid, knobs: GeneratorKnobs) -> list[list[str]]:
    new_cells = [[WALL for _ in range(grid.height)] for _ in range(grid.width)]
    for x in range(grid.width):
        for y in range(grid.height):
            if x == 0 or y == 0 or x == grid.width - 1 or y == grid.height - 1:
                new_cells[x][y] = WALL
                continue
            walls = _count_wall_neighbors(grid, x, y)
            if grid.cells[x][y] == WALL:
                new_cells[x][y] = WALL if walls >= knobs.cave_death_limit else FLOOR
            else:
                new_cells[x][y] = WALL if walls > knobs.cave_birth_limit else FLOOR
    return new_cells


def _count_wall_neighbors(grid: DungeonGrid, x: int, y: int) -> int:
    count = 0
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if not grid.in_bounds(nx, ny) or grid.cells[nx][ny] == WALL:
                count += 1
    return count


def _floor_components(grid: DungeonGrid) -> list[list[tuple[int, int]]]:
    seen: set[tuple[int, int]] = set()
    comps: list[list[tuple[int, int]]] = []
    for x in range(grid.width):
        for y in range(grid.height):
            if grid.cells[x][y] != FLOOR or (x, y) in seen:
                continue
            stack = [(x, y)]
            seen.add((x, y))
            comp = [(x, y)]
            while stack:
                cx, cy = stack.pop()
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if not grid.in_bounds(nx, ny) or (nx, ny) in seen:
                        continue
                    if grid.cells[nx][ny] != FLOOR:
                        continue
                    seen.add((nx, ny))
                    stack.append((nx, ny))
                    comp.append((nx, ny))
            comps.append(comp)
    return comps


def _rooms_from_open_space(grid: DungeonGrid, knobs: GeneratorKnobs, rng: random.Random) -> list[Room]:
    """Sample sparse room centers inside the cave for semantics / placement."""
    floors = grid.floor_positions()
    if not floors:
        return []
    rooms: list[Room] = []
    targets = max(3, min(knobs.room_count, len(floors) // 40))
    rng.shuffle(floors)
    for x, y in floors:
        if len(rooms) >= targets:
            break
        # Need some open neighborhood
        open_n = sum(
            1
            for dx in range(-2, 3)
            for dy in range(-2, 3)
            if grid.in_bounds(x + dx, y + dy) and grid.cells[x + dx][y + dy] == FLOOR
        )
        if open_n < 12:
            continue
        if any(abs(x - r.center[0]) + abs(y - r.center[1]) < 6 for r in rooms):
            continue
        size = min(5, knobs.room_min_size)
        rect = Rect(max(1, x - size // 2), max(1, y - size // 2), size, size)
        rooms.append(Room(id=len(rooms), rect=rect))
    return rooms


def _grow_cave_wing(grid: DungeonGrid, knobs: GeneratorKnobs, rng: random.Random) -> None:
    """Hybrid: attach a small cellular blob to a far room."""
    if not grid.rooms:
        return
    anchor = max(grid.rooms, key=lambda r: r.rect.x + r.rect.y)
    ax, ay = anchor.center
    blob_w = min(12, knobs.width // 3)
    blob_h = min(10, knobs.height // 3)
    ox = min(max(1, ax + rng.randint(2, 5)), knobs.width - blob_w - 1)
    oy = min(max(1, ay + rng.randint(-2, 4)), knobs.height - blob_h - 1)
    temp = DungeonGrid(blob_w + 2, blob_h + 2)
    cave_knobs = GeneratorKnobs(
        width=blob_w + 2,
        height=blob_h + 2,
        cave_fill_chance=0.42,
        cave_iterations=4,
        room_count=2,
    )
    temp = generate_cellular(cave_knobs, rng)
    for x in range(1, blob_w + 1):
        for y in range(1, blob_h + 1):
            if temp.cells[x][y] == FLOOR:
                grid.set(ox + x - 1, oy + y - 1, FLOOR)
    # Corridor from anchor into wing
    grid.carve_l_corridor(anchor.center, (ox + blob_w // 2, oy + blob_h // 2), knobs.corridor_width, True)
