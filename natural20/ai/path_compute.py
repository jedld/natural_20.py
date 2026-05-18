import heapq
import math
import copy
from natural20.item_library.door_object import DoorObject, DoorObjectWall
from natural20.item_library.chasm import Chasm
MAX_DISTANCE = 4_000_000

class PathCompute:
    def __init__(self, battle, map_, entity, ignore_opposing=False):
        self.entity = entity
        self.map = map_
        self.battle = battle
        self.ignore_opposing = ignore_opposing
        self.max_x, self.max_y = self.map.size
        # Tiles on which hazards (e.g. visible chasms) are intentionally allowed
        # because the caller asked to path *to* them. Populated per query.
        self._allowed_hazard_tiles = set()
        # Per-query caches to avoid redundant expensive Map method calls during A*.
        # These are cleared on each compute_path call so they don't leak across queries.
        self._objects_cache = {}          # (x, y, reveal_concealed) -> list
        self._difficult_cache = {}        # (x, y) -> bool
        self._passable_cache = {}         # (x, y, allow_squeeze, origin_tuple) -> bool
   
    def _clear_caches(self):
        """Reset per-query caches."""
        self._objects_cache.clear()
        self._difficult_cache.clear()
        self._passable_cache.clear()

    def _cached_objects_at(self, x, y, reveal_concealed=False):
        """Return cached result of ``map.objects_at`` for the given tile."""
        key = (x, y, reveal_concealed)
        cached = self._objects_cache.get(key)
        if cached is not None:
            return cached
        result = self.map.objects_at(x, y, reveal_concealed=reveal_concealed)
        self._objects_cache[key] = result
        return result

    def _cached_difficult_terrain(self, x, y):
        """Return cached difficult-terrain check for the tile."""
        key = (x, y)
        cached = self._difficult_cache.get(key)
        if cached is not None:
            return cached
        result = self.map.difficult_terrain(self.entity, x, y, self.battle)
        self._difficult_cache[key] = result
        return result

    def compute_path(self, source_x, source_y, destination_x, destination_y,
                     available_movement_cost=None,
                     accumulated_path=None,
                     door_navigation=False):
        """
        A* search from (source_x, source_y) to (destination_x, destination_y).

        Args:
            source_x, source_y: Starting coordinates
            destination_x, destination_y: Target coordinates
            available_movement_cost: Optional movement cost budget in feet
            accumulated_path: Optional list of (x,y) coordinates representing previous path segments
            door_navigation: Whether to enable door navigation, allowing the path to pass through doors.

        Returns:
            A list of (x, y) for the path or None if no path exists.
            If available_movement_cost is given, trims path that exceeds the cost in feet.
        """
        # Reset per-query caches so they don't leak across calls.
        self._clear_caches()

        # Validate and clamp coordinates to avoid out-of-bounds access
        if not (0 <= source_x < self.max_x and 0 <= source_y < self.max_y):
            return None
        # Clamp destination to map bounds
        destination_x = max(0, min(destination_x, self.max_x - 1))
        destination_y = max(0, min(destination_y, self.max_y - 1))

        # Initialize arrays
        distances = [[MAX_DISTANCE] * self.max_y for _ in range(self.max_x)]  # g-cost
        parents   = [[None]         * self.max_y for _ in range(self.max_x)]  # store parents to reconstruct path

        # Priority queue items: (f_cost, g_cost, (x, y))
        pq = []

        # Calculate initial cost from accumulated path if provided
        initial_cost = 0
        if accumulated_path:
            for i in range(0, len(accumulated_path) - 1):
                x1, y1 = accumulated_path[i]
                initial_cost += self.base_move_cost(x1, y1) * self.map.feet_per_grid

        if available_movement_cost is not None:
            available_movement_cost -= initial_cost

        # Allow the destination tile itself to be a hazard (intentional jump);
        # all other visible chasms are avoided. Also allow the source tile so
        # an entity already standing on a chasm can plan a path off of it.
        self._allowed_hazard_tiles = {(source_x, source_y), (destination_x, destination_y)}

        # Initialize start node
        distances[source_x][source_y] = 0
        start_heuristic = self.heuristic(source_x, source_y, destination_x, destination_y)
        heapq.heappush(pq, (start_heuristic, 0, (source_x, source_y)))

        # A* main loop
        while pq:
            current_f, current_g, (cx, cy) = heapq.heappop(pq)

            # If this is stale data (we already found a better route), skip
            if current_g > distances[cx][cy]:
                continue

            # If we've reached destination, we can stop
            if (cx, cy) == (destination_x, destination_y):
                break

            # Explore neighbors
            for (nx, ny), move_cost in self.get_neighbors(cx, cy, door_navigation=door_navigation):
                new_g = current_g + move_cost
                if new_g < distances[nx][ny]:
                    distances[nx][ny] = new_g
                    parents[nx][ny] = (cx, cy)

                    # f = g + h
                    h = self.heuristic(nx, ny, destination_x, destination_y)
                    f = new_g + h
                    heapq.heappush(pq, (f, new_g, (nx, ny)))

        # If destination is unreachable
        if distances[destination_x][destination_y] == MAX_DISTANCE:
            return None

        # Reconstruct path
        path = []
        node = (destination_x, destination_y)
        while node is not None:
            path.append(node)
            node = parents[node[0]][node[1]]

        path.reverse()  # get source -> destination

        # If we have a movement budget, trim
        if available_movement_cost is not None:
            path = self.trim_path_by_movement(path, distances, available_movement_cost)

        # If door navigation is enabled, truncate only at the first NON-PASSABLE door encountered
        # (i.e., skip truncation when the door is already open/passable).
        if door_navigation and len(path) > 1:
            for i in range(1, len(path)):
                px, py = path[i]
                if self._is_door_tile(px, py):
                    prev = path[i - 1]
                    # If we cannot legally move from prev -> (px, py) under normal rules,
                    # then this door is effectively closed/blocking. Truncate here.
                    if not self.map.bidirectionally_passable(self.entity, px, py, prev, self.battle, False,
                                                             ignore_opposing=self.ignore_opposing):
                        path = path[: i]
                        break

        return path

    def compute_paths_to_multiple_destinations(self, source_x, source_y, destinations, available_movement_cost=None, accumulated_path=None):
        """
        Compute paths to multiple destinations in a single pass using a modified A* algorithm.

        Args:
            source_x, source_y: Starting coordinates
            destinations: List of (x, y) tuples representing target coordinates
            available_movement_cost: Optional movement cost budget in feet
            accumulated_path: Optional list of (x,y) coordinates representing previous path segments

        Returns:
            A dictionary mapping each destination to its path: {(dest_x, dest_y): path, ...}
            If a destination is unreachable, its path will be None.
            If available_movement_cost is given, paths are trimmed to not exceed the cost in feet.
        """
        # Reset per-query caches so they don't leak across calls.
        self._clear_caches()

        # Validate source and filter destinations to map bounds
        if not (0 <= source_x < self.max_x and 0 <= source_y < self.max_y):
            return {dest: None for dest in destinations}
        in_bounds = []
        for dx, dy in destinations:
            if 0 <= dx < self.max_x and 0 <= dy < self.max_y:
                in_bounds.append((dx, dy))
        if not in_bounds:
            return {dest: None for dest in destinations}

        # Initialize arrays
        distances = [[MAX_DISTANCE] * self.max_y for _ in range(self.max_x)]  # g-cost
        parents   = [[None]         * self.max_y for _ in range(self.max_x)]  # store parents to reconstruct path

        # Track which destinations we've found paths for
        destinations_set = set(in_bounds)
        found_destinations = set()

        # Priority queue items: (f_cost, g_cost, (x, y))
        pq = []

        # Calculate initial cost from accumulated path if provided
        initial_cost = 0
        if accumulated_path:
            for i in range(0, len(accumulated_path) - 1):
                x1, y1 = accumulated_path[i]
                initial_cost += self.base_move_cost(x1, y1) * self.map.feet_per_grid

        if available_movement_cost is not None:
            available_movement_cost -= initial_cost

        # Allow the source tile and any explicit destinations as hazard
        # exceptions (intentional jumps); all other visible chasms are avoided.
        self._allowed_hazard_tiles = {(source_x, source_y)} | set(destinations_set)

        # Initialize start node
        distances[source_x][source_y] = 0

        # For multiple destinations, we need a heuristic that considers all destinations
        # We'll use the minimum heuristic to any destination
        min_heuristic = min(self.heuristic(source_x, source_y, dx, dy) for dx, dy in destinations_set)
        heapq.heappush(pq, (min_heuristic, 0, (source_x, source_y)))

        # A* main loop
        while pq and len(found_destinations) < len(destinations):
            current_f, current_g, (cx, cy) = heapq.heappop(pq)

            # If this is stale data (we already found a better route), skip
            if current_g > distances[cx][cy]:
                continue

            # Check if we've reached a destination
            if (cx, cy) in destinations_set and (cx, cy) not in found_destinations:
                found_destinations.add((cx, cy))

            # Explore neighbors
            for (nx, ny), move_cost in self.get_neighbors(cx, cy):
                new_g = current_g + move_cost
                if new_g < distances[nx][ny]:
                    distances[nx][ny] = new_g
                    parents[nx][ny] = (cx, cy)

                    # For multiple destinations, use the minimum heuristic to any remaining destination
                    remaining_destinations = destinations_set - found_destinations
                    if remaining_destinations:
                        min_h = min(self.heuristic(nx, ny, dx, dy) for dx, dy in remaining_destinations)
                        f = new_g + min_h
                        heapq.heappush(pq, (f, new_g, (nx, ny)))
                    else:
                        # If all destinations have been found, we can stop
                        break

        # Reconstruct paths for all destinations
        result = {dest: None for dest in destinations}
        for dest_x, dest_y in destinations_set:
            # If destination is unreachable
            if distances[dest_x][dest_y] == MAX_DISTANCE:
                result[(dest_x, dest_y)] = None
                continue

            # Reconstruct path
            path = []
            node = (dest_x, dest_y)
            while node is not None:
                path.append(node)
                node = parents[node[0]][node[1]]

            path.reverse()  # get source -> destination

            # If we have a movement budget, trim
            if available_movement_cost is not None:
                path = self.trim_path_by_movement(path, distances, available_movement_cost)

            result[(dest_x, dest_y)] = path

        return result

    def _is_door_tile(self, x, y) -> bool:
        try:
            objs = self._cached_objects_at(x, y)
        except Exception:
            return False
        for obj in objs:
            if isinstance(obj, (DoorObject, DoorObjectWall)):
                return True
            # Fallback: some door variants may expose kind_of_door
            if hasattr(obj, 'kind_of_door') and obj.kind_of_door():
                return True
        return False

    def _is_avoidable_hazard(self, x, y) -> bool:
        """Return True if the tile contains a hazard the entity should avoid
        when planning a path. Currently this means a non-concealed ``Chasm``
        and a non-flying entity. Concealed chasms are not avoided because the
        entity cannot reasonably know about them.
        """
        if self.entity is not None and getattr(self.entity, 'is_flying', None):
            try:
                if self.entity.is_flying():
                    return False
            except Exception:
                pass
        try:
            objs = self._cached_objects_at(x, y, reveal_concealed=False)
        except TypeError:
            try:
                objs = self._cached_objects_at(x, y)
            except Exception:
                return False
        except Exception:
            return False
        for obj in objs:
            if isinstance(obj, Chasm) and not obj.concealed():
                return True
        return False

    def _cached_passable(self, nx, ny, origin, allow_squeeze):
        """Return cached result of ``map.bidirectionally_passable`` for neighbor checks."""
        origin_tuple = (origin[0], origin[1]) if isinstance(origin, (list, tuple)) else origin
        key = (nx, ny, allow_squeeze, origin_tuple, self.ignore_opposing)
        cached = self._passable_cache.get(key)
        if cached is not None:
            return cached
        result = self.map.bidirectionally_passable(
            self.entity, nx, ny, origin, self.battle, allow_squeeze,
            ignore_opposing=self.ignore_opposing)
        self._passable_cache[key] = bool(result)
        return result

    def get_neighbors(self, x, y, door_navigation: bool = False):
        """
        Return a list of tuples: [((nx, ny), move_cost), ...].
        Similar to Dijkstra code, but we don't need separate 'squeeze' vs. normal
        calls; we can decide the cost or if passable inside here.
        """
        neighbors = []

        def diagonal_clear(dx, dy, allow_squeeze: bool) -> bool:
            """
            For diagonal steps, ensure we don't slip through solid corners.
            Allow the diagonal if at least one of the orthogonal adjacents is traversable
            under the same squeeze rule.
            """
            if abs(dx) != 1 or abs(dy) != 1:
                return True
            ax, ay = x + dx, y          # horizontal neighbor
            bx, by = x, y + dy    # vertical neighbor
            adj1_ok = self._cached_passable(ax, ay, (x, y), allow_squeeze)
            adj2_ok = self._cached_passable(bx, by, (x, y), allow_squeeze)
            # If door navigation is on, treat door tiles as acceptable for the orthogonal clearance
            if door_navigation:
                if not adj1_ok and self._is_door_tile(ax, ay):
                    adj1_ok = True
                if not adj2_ok and self._is_door_tile(bx, by):
                    adj2_ok = True
            return adj1_ok or adj2_ok

        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx = x + dx
                ny = y + dy
                if not (0 <= nx < self.max_x and 0 <= ny < self.max_y):
                    continue

                # Avoid stepping into known hazards (e.g. visible chasms)
                # unless the caller marked this tile as an intentional target.
                if self._is_avoidable_hazard(nx, ny) and (nx, ny) not in self._allowed_hazard_tiles:
                    continue

                # Try normal passable
                if diagonal_clear(dx, dy, allow_squeeze=False) and \
                   (self._cached_passable(nx, ny, (x, y), False) or
                    (door_navigation and self._is_door_tile(nx, ny))):
                    move_cost = self.base_move_cost(nx, ny, src=(x, y))
                    neighbors.append(((nx, ny), move_cost))
                # Otherwise, if not normal passable, check if passable with squeeze
                elif diagonal_clear(dx, dy, allow_squeeze=True) and \
                     (self._cached_passable(nx, ny, (x, y), True) or
                      (door_navigation and self._is_door_tile(nx, ny))):
                    # e.g., let's define squeeze cost = 2
                    move_cost = self.base_move_cost(nx, ny, src = (x, y)) + 1
                    if self.entity.prone():
                        move_cost += 1
                    neighbors.append(((nx, ny), move_cost))

        return neighbors

    def base_move_cost(self, x, y, src=None):
        """
        If the terrain is difficult or the entity is prone, adjust cost accordingly.
        """
        is_difficult = self._cached_difficult_terrain(x, y)
        cost = 2 if is_difficult and not self.entity.is_flying() else 1
        if self.entity.prone():
            cost += 1
        if src:
            # if diagonal add 0.5 to the cost
            if (src[0] != x and src[1] != y):
                cost += 0.1
        return cost

    def heuristic(self, cx, cy, dx, dy):
        """
        Example Euclidean (straight-line) distance.
        For grid movement, a typical approach is:
            - Euclidean:   math.sqrt((cx - dx)**2 + (cy - dy)**2)
            - Manhattan:   abs(cx - dx) + abs(cy - dy)
        Choose whichever is suitable or consistent with your movement rules.
        """
        # Euclidean distance
        return math.sqrt((cx - dx)**2 + (cy - dy)**2)

    def trim_path_by_movement(self, path, distances, available_movement_cost):
        """
        After building the path, remove nodes beyond a certain movement cost (in feet).
        """
        trimmed = []
        for (px, py) in path:
            # Convert grid cost to feet
            g_cost_in_feet = distances[px][py] * self.map.feet_per_grid
            if g_cost_in_feet <= available_movement_cost:
                trimmed.append((px, py))
            else:
                # Once we exceed movement, no need to keep trailing nodes
                break
        return trimmed

    # ------------------------------------------------------------------
    # Cross-map pathfinding (teleporter-aware)
    # ------------------------------------------------------------------
    @staticmethod
    def _iter_teleporters_on(map_):
        """Yield ``(teleporter_obj, x, y)`` for each non-Chasm Teleporter on
        ``map_`` that has a usable ``target_map`` link. Chasms are intentionally
        skipped — they are hazards, not stairs."""
        from natural20.item_library.teleporter import Teleporter as _Teleporter
        try:
            items = list(map_.interactable_objects.items())
        except Exception:
            return
        for obj, pos in items:
            if not isinstance(obj, _Teleporter):
                continue
            # Skip chasms: they are hazards filtered by ``_is_avoidable_hazard``
            # and must not be treated as a free portal during planning.
            if isinstance(obj, Chasm):
                continue
            if not getattr(obj, 'target_map', None):
                continue
            if not getattr(obj, 'target_position', None):
                continue
            try:
                x, y = int(pos[0]), int(pos[1])
            except Exception:
                continue
            yield obj, x, y

    def compute_cross_map_path(self, source_map, source_x, source_y,
                               target_map, target_x, target_y,
                               max_segments: int = 8):
        """A* over a graph of (map, x, y) states linked by teleporters.

        Each segment of the result is a single-map sub-path the entity must
        walk; consecutive segments are stitched by stepping onto a teleporter
        whose ``target_map`` lands them on the next segment's start tile.

        Args:
            source_map: starting :class:`Map` instance.
            source_x, source_y: starting tile.
            target_map: destination :class:`Map` instance.
            target_x, target_y: destination tile.
            max_segments: bail-out cap to keep planning bounded across very
                large dungeons.

        Returns:
            A list of dicts ``[{ 'map': map_obj, 'path': [(x,y), ...],
            'teleporter': obj_or_None, 'next_map': map_or_None }]`` or
            ``None`` if no cross-map route exists. The first segment starts at
            ``(source_x, source_y)`` and the final segment ends at
            ``(target_x, target_y)``.
        """
        if source_map is None or target_map is None:
            return None
        if source_map is target_map:
            path = self._compute_path_on(source_map, source_x, source_y,
                                         target_x, target_y)
            if path is None:
                return None
            return [{
                'map': source_map,
                'path': path,
                'teleporter': None,
                'next_map': None,
            }]

        # State = (map_id, x, y). Edges: teleporter portals (zero-cost), and
        # a virtual edge from any teleporter on ``target_map`` directly to the
        # goal weighted by single-map path length.
        # For tractability we enumerate teleporter nodes only.
        visited = set()
        # priority queue of (cost, sequence, state, parent_state, segment_path,
        #                    teleporter, current_map)
        pq = []
        seq = 0

        def push(state, cost, parent, path, tport, cur_map):
            nonlocal seq
            seq += 1
            heapq.heappush(pq, (cost, seq, state, parent, path, tport, cur_map))

        start_state = (id(source_map), source_x, source_y)
        push(start_state, 0.0, None, None, None, source_map)

        # Predecessor table set at pop-time so Dijkstra optimality holds.
        parents = {}  # state -> (parent_state, segment_path, teleporter, segment_map)
        maps_by_id = {id(source_map): source_map, id(target_map): target_map}

        goal_state = (id(target_map), target_x, target_y)
        # Bound the search to avoid pathological exploration in huge dungeons.
        max_pops = max(64, max_segments * 32)
        pops = 0

        while pq and pops < max_pops:
            pops += 1
            cost, _, state, parent, seg_path, tport_in, seg_map = heapq.heappop(pq)
            if state in visited:
                continue
            visited.add(state)
            if parent is not None:
                parents[state] = (parent, seg_path, tport_in, seg_map)

            map_id, x, y = state
            current_map = maps_by_id.get(map_id)
            if current_map is None:
                continue

            # Try direct hop to goal if we are on the target map.
            if current_map is target_map:
                direct = self._compute_path_on(current_map, x, y,
                                               target_x, target_y)
                if direct is not None:
                    parents[goal_state] = (state, direct, None, current_map)
                    return self._reconstruct_cross_map(goal_state, parents)

            # Expand via teleporters on the current map.
            for tport, tx, ty in self._iter_teleporters_on(current_map):
                if (x, y) == (tx, ty):
                    seg = [(x, y)]
                else:
                    seg = self._compute_path_on(current_map, x, y, tx, ty)
                    if seg is None:
                        continue
                next_map = current_map.linked_maps.get(tport.target_map)
                if next_map is None:
                    continue
                maps_by_id.setdefault(id(next_map), next_map)
                tpos = tport.target_position
                try:
                    nxt_state = (id(next_map), int(tpos[0]), int(tpos[1]))
                except Exception:
                    continue
                if nxt_state in visited:
                    continue
                # Cost = current segment length (in tiles); teleport hop free.
                push(nxt_state, cost + len(seg), state, seg, tport, current_map)

        return None

    def _compute_path_on(self, map_, sx, sy, tx, ty):
        """Compute a single-map path on ``map_`` while preserving the
        configured ``ignore_opposing`` and entity context. Returns the raw
        tile list (no movement-cost trimming) or ``None``."""
        helper = PathCompute(self.battle, map_, self.entity,
                             ignore_opposing=self.ignore_opposing)
        return helper.compute_path(sx, sy, tx, ty)

    def _reconstruct_cross_map(self, goal_state, parents):
        chain = []
        state = goal_state
        while state in parents:
            parent_state, seg, tport, cur_map = parents[state]
            chain.append({
                'map': cur_map,
                'path': seg,
                'teleporter': tport,
                'next_map': None,  # filled in below
            })
            state = parent_state
        chain.reverse()
        # Fill ``next_map`` so callers know where each teleporter lands.
        for segment in chain:
            tport = segment['teleporter']
            if tport is None:
                continue
            next_map = segment['map'].linked_maps.get(tport.target_map)
            segment['next_map'] = next_map
        return chain
