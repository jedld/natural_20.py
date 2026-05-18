"""Serializable pathfinding grid for client-side A* (mirrors PathCompute rules)."""

from __future__ import annotations

import heapq
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from natural20.ai.path_compute import MAX_DISTANCE, PathCompute

# Outgoing edge order: same nested loops as PathCompute.get_neighbors
DIR_OFFSETS: Tuple[Tuple[int, int], ...] = (
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1), (0, 1),
    (1, -1), (1, 0), (1, 1),
)


def _dir_index(dx: int, dy: int) -> Optional[int]:
    for i, (odx, ody) in enumerate(DIR_OFFSETS):
        if odx == dx and ody == dy:
            return i
    return None


def build_pathfinding_snapshot(
    battle_map,
    entity,
    battle=None,
    *,
    ignore_opposing: bool = False,
    allowed_hazard_tiles: Optional[Sequence[Tuple[int, int]]] = None,
) -> Dict[str, Any]:
    """Precompute tile flags and passability bits for JS PathCompute."""
    w, h = int(battle_map.size[0]), int(battle_map.size[1])
    pc = PathCompute(battle, battle_map, entity, ignore_opposing=ignore_opposing)
    allowed = set(allowed_hazard_tiles or ())

    difficult: List[bool] = []
    hazard: List[bool] = []
    door: List[bool] = []
    blocked: List[bool] = []
    pass_normal: List[int] = []
    pass_squeeze: List[int] = []

    for y in range(h):
        for x in range(w):
            difficult.append(bool(battle_map.difficult_terrain(entity, x, y, battle)))
            hazard.append(bool(pc._is_avoidable_hazard(x, y)))
            is_door = bool(pc._is_door_tile(x, y))
            door.append(is_door)
            blocked.append(bool(battle_map.base_map[x][y] == '#'))

            pn = 0
            ps = 0
            for di, (dx, dy) in enumerate(DIR_OFFSETS):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < w and 0 <= ny < h):
                    continue
                if pc._is_avoidable_hazard(nx, ny) and (nx, ny) not in allowed:
                    continue

                def _diag_clear(allow_squeeze: bool) -> bool:
                    if abs(dx) != 1 or abs(dy) != 1:
                        return True
                    ax, ay = x + dx, y
                    bx, by = x, y + dy
                    adj1 = pc._cached_passable(ax, ay, (x, y), allow_squeeze)
                    adj2 = pc._cached_passable(bx, by, (x, y), allow_squeeze)
                    return adj1 or adj2

                if _diag_clear(False) and pc._cached_passable(nx, ny, (x, y), False):
                    pn |= 1 << di
                elif _diag_clear(True) and pc._cached_passable(nx, ny, (x, y), True):
                    ps |= 1 << di

            pass_normal.append(pn)
            pass_squeeze.append(ps)

    return {
        'version': 1,
        'width': w,
        'height': h,
        'feet_per_grid': int(getattr(battle_map, 'feet_per_grid', 5) or 5),
        'entity': {
            'prone': bool(entity.prone()) if entity is not None and hasattr(entity, 'prone') else False,
            'flying': bool(entity.is_flying()) if entity is not None and hasattr(entity, 'is_flying') else False,
        },
        'difficult': difficult,
        'hazard': hazard,
        'door': door,
        'blocked': blocked,
        'pass_normal': pass_normal,
        'pass_squeeze': pass_squeeze,
    }


def snapshot_allows_hazard(snapshot: Dict[str, Any], tiles: Sequence[Tuple[int, int]]) -> Dict[str, Any]:
    """Return a shallow copy of *snapshot* with extra hazard exceptions (for A* goals)."""
    out = dict(snapshot)
    allowed = set(tiles)
    w, h = int(out['width']), int(out['height'])
    hazard = list(out.get('hazard') or [])
    for x, y in allowed:
        if 0 <= x < w and 0 <= y < h:
            hazard[y * w + x] = False
    out['allowed_hazard'] = [[int(x), int(y)] for x, y in allowed]
    out['hazard'] = hazard
    return out


class SnapshotPathCompute:
    """A* on a :func:`build_pathfinding_snapshot` payload (same rules as PathCompute)."""

    def __init__(self, snapshot: Dict[str, Any]):
        self.snapshot = snapshot
        self.width = int(snapshot['width'])
        self.height = int(snapshot['height'])
        self.feet_per_grid = int(snapshot.get('feet_per_grid', 5) or 5)
        ent = snapshot.get('entity') or {}
        self.prone = bool(ent.get('prone'))
        self.flying = bool(ent.get('flying'))
        self._difficult = list(snapshot.get('difficult') or [])
        self._hazard = list(snapshot.get('hazard') or [])
        self._door = list(snapshot.get('door') or [])
        self._pass_normal = list(snapshot.get('pass_normal') or [])
        self._pass_squeeze = list(snapshot.get('pass_squeeze') or [])
        self._allowed_hazard: set = set()

    def _idx(self, x: int, y: int) -> int:
        return y * self.width + x

    def _tile(self, arr: List, x: int, y: int) -> bool:
        return bool(arr[self._idx(x, y)])

    def _has_pass(self, arr: List[int], x: int, y: int, di: int) -> bool:
        return bool(arr[self._idx(x, y)] & (1 << di))

    def _is_door(self, x: int, y: int) -> bool:
        return self._tile(self._door, x, y)

    def _is_hazard(self, x: int, y: int) -> bool:
        return self._tile(self._hazard, x, y)

    def _base_move_cost(self, x: int, y: int, src: Optional[Tuple[int, int]] = None) -> float:
        cost = 2.0 if self._tile(self._difficult, x, y) and not self.flying else 1.0
        if self.prone:
            cost += 1.0
        if src and src[0] != x and src[1] != y:
            cost += 0.1
        return cost

    def _heuristic(self, cx: int, cy: int, dx: int, dy: int) -> float:
        return math.sqrt((cx - dx) ** 2 + (cy - dy) ** 2)

    def _diagonal_clear(self, x: int, y: int, dx: int, dy: int, allow_squeeze: bool,
                        door_navigation: bool) -> bool:
        if abs(dx) != 1 or abs(dy) != 1:
            return True
        ax, ay = x + dx, y
        bx, by = x, y + dy
        pass_arr = self._pass_squeeze if allow_squeeze else self._pass_normal
        di_a = _dir_index(dx, 0)
        di_b = _dir_index(0, dy)
        adj1 = (di_a is not None and self._has_pass(pass_arr, x, y, di_a))
        adj2 = (di_b is not None and self._has_pass(pass_arr, x, y, di_b))
        if door_navigation:
            if not adj1 and self._is_door(ax, ay):
                adj1 = True
            if not adj2 and self._is_door(bx, by):
                adj2 = True
        return adj1 or adj2

    def _get_neighbors(self, x: int, y: int, door_navigation: bool = False):
        neighbors = []
        for di, (dx, dy) in enumerate(DIR_OFFSETS):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < self.width and 0 <= ny < self.height):
                continue
            if self._is_hazard(nx, ny) and (nx, ny) not in self._allowed_hazard:
                continue
            if self._diagonal_clear(x, y, dx, dy, False, door_navigation) and (
                self._has_pass(self._pass_normal, x, y, di)
                or (door_navigation and self._is_door(nx, ny))
            ):
                neighbors.append(((nx, ny), self._base_move_cost(nx, ny, (x, y))))
            elif self._diagonal_clear(x, y, dx, dy, True, door_navigation) and (
                self._has_pass(self._pass_squeeze, x, y, di)
                or (door_navigation and self._is_door(nx, ny))
            ):
                move_cost = self._base_move_cost(nx, ny, (x, y)) + 1.0
                if self.prone:
                    move_cost += 1.0
                neighbors.append(((nx, ny), move_cost))
        return neighbors

    def compute_path(
        self,
        source_x: int,
        source_y: int,
        destination_x: int,
        destination_y: int,
        *,
        available_movement_cost: Optional[float] = None,
        accumulated_path: Optional[Sequence[Tuple[int, int]]] = None,
        door_navigation: bool = False,
    ) -> Optional[List[Tuple[int, int]]]:
        if not (0 <= source_x < self.width and 0 <= source_y < self.height):
            return None
        destination_x = max(0, min(destination_x, self.width - 1))
        destination_y = max(0, min(destination_y, self.height - 1))

        distances = [[MAX_DISTANCE] * self.height for _ in range(self.width)]
        parents = [[None] * self.height for _ in range(self.width)]
        pq: List[Tuple[float, float, Tuple[int, int]]] = []

        initial_cost = 0.0
        if accumulated_path:
            for i in range(len(accumulated_path) - 1):
                x1, y1 = accumulated_path[i]
                initial_cost += self._base_move_cost(x1, y1) * self.feet_per_grid
        if available_movement_cost is not None:
            available_movement_cost -= initial_cost

        self._allowed_hazard = {(source_x, source_y), (destination_x, destination_y)}
        distances[source_x][source_y] = 0
        heapq.heappush(
            pq,
            (self._heuristic(source_x, source_y, destination_x, destination_y), 0.0, (source_x, source_y)),
        )

        while pq:
            _f, current_g, (cx, cy) = heapq.heappop(pq)
            if current_g > distances[cx][cy]:
                continue
            if (cx, cy) == (destination_x, destination_y):
                break
            for (nx, ny), move_cost in self._get_neighbors(cx, cy, door_navigation=door_navigation):
                new_g = current_g + move_cost
                if new_g < distances[nx][ny]:
                    distances[nx][ny] = new_g
                    parents[nx][ny] = (cx, cy)
                    h = self._heuristic(nx, ny, destination_x, destination_y)
                    heapq.heappush(pq, (new_g + h, new_g, (nx, ny)))

        if distances[destination_x][destination_y] == MAX_DISTANCE:
            return None

        path: List[Tuple[int, int]] = []
        node: Optional[Tuple[int, int]] = (destination_x, destination_y)
        while node is not None:
            path.append(node)
            node = parents[node[0]][node[1]]
        path.reverse()

        if available_movement_cost is not None:
            trimmed: List[Tuple[int, int]] = []
            for px, py in path:
                if distances[px][py] * self.feet_per_grid <= available_movement_cost:
                    trimmed.append((px, py))
                else:
                    break
            path = trimmed

        if door_navigation and len(path) > 1:
            for i in range(1, len(path)):
                px, py = path[i]
                if not self._is_door(px, py):
                    continue
                prev = path[i - 1]
                pdx = px - prev[0]
                pdy = py - prev[1]
                di = _dir_index(pdx, pdy)
                if di is None or not self._has_pass(self._pass_normal, prev[0], prev[1], di):
                    path = path[:i]
                    break

        return path


def compute_path_from_snapshot(
    snapshot: Dict[str, Any],
    source_x: int,
    source_y: int,
    destination_x: int,
    destination_y: int,
    **kwargs,
) -> Optional[List[Tuple[int, int]]]:
    return SnapshotPathCompute(snapshot).compute_path(
        source_x, source_y, destination_x, destination_y, **kwargs
    )
