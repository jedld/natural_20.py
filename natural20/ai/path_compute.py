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
            objs = self.map.objects_at(x, y)
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
            objs = self.map.objects_at(x, y, reveal_concealed=False)
        except TypeError:
            try:
                objs = self.map.objects_at(x, y)
            except Exception:
                return False
        except Exception:
            return False
        for obj in objs:
            if isinstance(obj, Chasm) and not obj.concealed():
                return True
        return False

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
            adj1_ok = self.map.bidirectionally_passable(self.entity, ax, ay, (x, y), self.battle, allow_squeeze,
                                                        ignore_opposing=self.ignore_opposing)
            adj2_ok = self.map.bidirectionally_passable(self.entity, bx, by, (x, y), self.battle, allow_squeeze,
                                                        ignore_opposing=self.ignore_opposing)
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
                   (self.map.bidirectionally_passable(self.entity, nx, ny, (x, y), self.battle, False,
                                    ignore_opposing=self.ignore_opposing) or
                    (door_navigation and self._is_door_tile(nx, ny))):
                    move_cost = self.base_move_cost(nx, ny, src = (x, y))
                    neighbors.append(((nx, ny), move_cost))
                # Otherwise, if not normal passable, check if passable with squeeze
                elif diagonal_clear(dx, dy, allow_squeeze=True) and \
                     (self.map.bidirectionally_passable(self.entity, nx, ny, (x, y), self.battle, True,
                                    ignore_opposing=self.ignore_opposing) or
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
        cost = 2 if self.map.difficult_terrain(self.entity, x, y, self.battle) and not self.entity.is_flying() else 1
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
