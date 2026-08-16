"""Convert solid ``#`` occupancy into directional thin walls (and doors).

Filled-cell classifiers (watercolor floorplans, per-tile color occupancy) paint
masonry as impassable ``#``. Natural20's Death House convention puts a walkable
``StoneWallDirectional`` token on the cell and only blocks the inked edges.

A one-cell ``#`` between two floor rooms is a missing door, not a thin wall —
directional tokens still block crossing that edge. ``punch_single_cell_doors``
opens one ``-``/``|`` per pair of sizable rooms, then leftover outline ``#``
becomes ``┌┬┐├┤└┘HZ``. Thick blobs and the map frame stay ``#``.
"""

from __future__ import annotations

from collections import deque
from itertools import combinations
from typing import Any

from natural20.map_import.taxonomy import (
    DIRECTIONAL_WALL_TOKENS,
    directional_wall_mappings,
    legend_entry,
    mapping_for_wall_edges,
)

SOLID = "#"
FLOOR = {".", "-", "|"}


def prepare_occupancy_walls(rows: list[str], *, keep_frame: bool = True, min_room: int = 5) -> list[str]:
    """Punch 1-cell doors between rooms, then convert remaining outlines."""
    return occupancy_to_thin_walls(
        punch_single_cell_doors(rows, min_room=min_room, keep_frame=keep_frame),
        keep_frame=keep_frame,
    )


def punch_single_cell_doors(rows: list[str], *, min_room: int = 5, keep_frame: bool = True) -> list[str]:
    """Open one door on each 1-cell ``#`` gate between sizable floor regions."""
    if not rows:
        return rows
    height = len(rows)
    width = len(rows[0])
    comps = _floor_components(rows)
    sizable = {i for i, cells in enumerate(comps) if len(cells) >= min_room}
    if len(sizable) < 2:
        return rows
    label: dict[tuple[int, int], int] = {}
    centroids: dict[int, tuple[float, float]] = {}
    for i, cells in enumerate(comps):
        for cell in cells:
            label[cell] = i
        xs = [c[0] for c in cells]
        ys = [c[1] for c in cells]
        centroids[i] = (sum(xs) / len(xs), sum(ys) / len(ys))

    gates: dict[tuple[int, int], list[tuple[int, int, str]]] = {}
    for y in range(height):
        for x in range(width):
            if rows[y][x] != SOLID:
                continue
            if keep_frame and (x == 0 or y == 0 or x == width - 1 or y == height - 1):
                continue
            adj: dict[int, list[tuple[int, int]]] = {}
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (x + dx, y + dy)
                if n in label and label[n] in sizable:
                    adj.setdefault(label[n], []).append((dx, dy))
            if len(adj) < 2:
                continue
            token = _door_token(adj)
            for a, b in combinations(sorted(adj), 2):
                gates.setdefault((a, b), []).append((x, y, token))

    out = [list(row) for row in rows]
    for (a, b), candidates in gates.items():
        smaller = a if len(comps[a]) <= len(comps[b]) else b
        cx, cy = centroids[smaller]
        x, y, token = min(candidates, key=lambda g: (g[0] - cx) ** 2 + (g[1] - cy) ** 2)
        out[y][x] = token
    return ["".join(row) for row in out]


def occupancy_to_thin_walls(rows: list[str], *, keep_frame: bool = True) -> list[str]:
    """Replace 1-cell ``#`` outlines with ``┌┬┐├┤└┘HZ``; leave filled masonry."""
    if not rows:
        return rows
    height = len(rows)
    width = len(rows[0])
    out = [list(row) for row in rows]
    for y in range(height):
        for x in range(width):
            if rows[y][x] != SOLID:
                continue
            if keep_frame and (x == 0 or y == 0 or x == width - 1 or y == height - 1):
                continue
            north = _solid_at(rows, x, y - 1, width, height)
            east = _solid_at(rows, x + 1, y, width, height)
            south = _solid_at(rows, x, y + 1, width, height)
            west = _solid_at(rows, x - 1, y, width, height)
            mapping = mapping_for_wall_edges(not north, not east, not south, not west)
            if mapping is not None:
                out[y][x] = mapping.base_token
    return ["".join(row) for row in out]


def thin_wall_legend(rows: list[str]) -> dict[str, Any]:
    """Legend entries for directional wall tokens that appear in ``rows``."""
    present = {ch for row in rows for ch in row}
    legend: dict[str, Any] = {}
    for mapping in directional_wall_mappings():
        if mapping.base_token not in present:
            continue
        entry = legend_entry(mapping)
        if entry:
            legend[mapping.base_token] = entry
    return legend


def merge_thin_wall_legend(legend: dict[str, Any], rows: list[str]) -> dict[str, Any]:
    """Add missing directional-wall legend keys; do not overwrite existing ones."""
    out = dict(legend)
    for token, entry in thin_wall_legend(rows).items():
        out.setdefault(token, entry)
    return out


def is_occupancy_walkable(ch: str) -> bool:
    return ch in FLOOR or ch in DIRECTIONAL_WALL_TOKENS


def _floor_components(rows: list[str]) -> list[list[tuple[int, int]]]:
    height = len(rows)
    width = len(rows[0])
    seen = [[False] * width for _ in range(height)]
    comps: list[list[tuple[int, int]]] = []
    for y in range(height):
        for x in range(width):
            if seen[y][x] or rows[y][x] not in FLOOR:
                continue
            cells: list[tuple[int, int]] = []
            queue = deque([(x, y)])
            seen[y][x] = True
            while queue:
                cx, cy = queue.popleft()
                cells.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < width and 0 <= ny < height and not seen[ny][nx] and rows[ny][nx] in FLOOR:
                        seen[ny][nx] = True
                        queue.append((nx, ny))
            comps.append(cells)
    comps.sort(key=len, reverse=True)
    return comps


def _door_token(adj: dict[int, list[tuple[int, int]]]) -> str:
    """``|`` opens east-west (door in a north-south wall); ``-`` opens north-south."""
    deltas = [d for dirs in adj.values() for d in dirs]
    ew = any(dx != 0 for dx, _dy in deltas)
    ns = any(dy != 0 for _dx, dy in deltas)
    if ew and not ns:
        return "|"
    if ns and not ew:
        return "-"
    return "|" if abs(sum(dx for dx, _dy in deltas)) >= abs(sum(dy for _dx, dy in deltas)) else "-"


def _solid_at(rows: list[str], x: int, y: int, width: int, height: int) -> bool:
    if x < 0 or y < 0 or x >= width or y >= height:
        return True
    return rows[y][x] == SOLID
