import heapq
import math

MAX_DISTANCE = 4_000_000

class PathCompute:
    def __init__(self, battle, map_, entity, ignore_opposing=False):
        self.entity = entity
        self.map = map_
        self.battle = battle
        self.ignore_opposing = ignore_opposing
        self.max_x, self.max_y = self.map.size

    def compute_path(self, source_x, source_y, destination_x, destination_y, available_movement_cost=None):
        """
        A* search from (source_x, source_y) to (destination_x, destination_y).

        Returns:
            A list of (x, y) for the path or None if no path exists.
            If available_movement_cost is given, trims path that exceeds the cost in feet.
        """

        # Initialize arrays
        distances = [[MAX_DISTANCE] * self.max_y for _ in range(self.max_x)]  # g-cost
        parents   = [[None]         * self.max_y for _ in range(self.max_x)]  # store parents to reconstruct path
        
        # Priority queue items: (f_cost, g_cost, (x, y))
        #  - f_cost = g_cost + heuristic(x,y)
        #  - g_cost = actual distance from source
        pq = []

        # Initialize start
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
            for (nx, ny), move_cost in self.get_neighbors(cx, cy):
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
        
        return path

    def get_neighbors(self, x, y):
        """
        Return a list of tuples: [((nx, ny), move_cost), ...].
        Similar to Dijkstra code, but we don't need separate 'squeeze' vs. normal
        calls; we can decide the cost or if passable inside here.
        """
        neighbors = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx = x + dx
                ny = y + dy
                if not (0 <= nx < self.max_x and 0 <= ny < self.max_y):
                    continue

                # Try normal passable
                if self.map.passable(self.entity, nx, ny, self.battle, False,
                                     origin=(x, y),
                                     ignore_opposing=self.ignore_opposing):
                    move_cost = self.base_move_cost(nx, ny)
                    neighbors.append(((nx, ny), move_cost))
                # Otherwise, if not normal passable, check if passable with squeeze
                elif self.map.passable(self.entity, nx, ny, self.battle, True,
                                       origin=(x, y),
                                       ignore_opposing=self.ignore_opposing):
                    # e.g., let's define squeeze cost = 2
                    move_cost = 2
                    if self.entity.prone():
                        move_cost += 1
                    neighbors.append(((nx, ny), move_cost))
        
        return neighbors

    def base_move_cost(self, x, y):
        """
        If the terrain is difficult or the entity is prone, adjust cost accordingly.
        """
        cost = 2 if self.map.difficult_terrain(self.entity, x, y, self.battle) else 1
        if self.entity.prone():
            cost += 1
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
