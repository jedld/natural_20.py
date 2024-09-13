import heapq
import math

MAX_DISTANCE = 4_000_000

class PathCompute:
    def __init__(self, battle, map, entity):
        self.entity = entity
        self.map = map
        self.battle = battle
        self.max_x, self.max_y = self.map.size

    def build_structures(self, source_x, source_y):
        self.pq = []
        self.visited_nodes = set()

        self.distances = [[MAX_DISTANCE for _ in range(self.max_y)] for _ in range(self.max_x)]

        self.current_node = (source_x, source_y)
        self.distances[source_x][source_y] = 0
        self.visited_nodes.add(self.current_node)

    def backtrace(self, source_x, source_y, destination_x, destination_y, show_cost=False, available_movement_cost=None):
        path = []
        current_node = (destination_x, destination_y)
        if self.distances[destination_x][destination_y] == MAX_DISTANCE:
            return None  # No route!

        path.append(current_node)
        cost = self.distances[destination_x][destination_y]
        visited_nodes = set()
        visited_nodes.add(current_node)

        while True:
            adjacent_squares = self.get_adjacent_from(*current_node)
            adjacent_squares.update(self.get_adjacent_from(*current_node, squeeze=True))

            min_node = None
            min_distance = None

            for node in adjacent_squares - visited_nodes:
                line_distance = math.sqrt((destination_x - node[0])**2 + (destination_y - node[1])**2)
                current_distance = self.distances[node[0]][node[1]] + line_distance / MAX_DISTANCE
                if min_node is None or current_distance < min_distance:
                    min_distance = current_distance
                    min_node = node

            if min_node is None:
                return None

            path.append(min_node)
            current_node = min_node
            visited_nodes.add(current_node)
            if current_node == (source_x, source_y):
                break
        if available_movement_cost:
            trimmed_path = []
            for i in range(0, len(path)):
                destination_x, destination_y = path[i]
                incremental_cost = self.distances[destination_x][destination_y] * self.map.feet_per_grid
                # print(f"Checking {destination_x}, {destination_y} with {available_movement_cost} cost {incremental_cost}")
                if incremental_cost <= available_movement_cost:
                    trimmed_path.append(path[i])
            path = trimmed_path

        return (path[::-1], cost) if show_cost else path[::-1]

    def path(self, destination=None):
        while True:
            distance = self.distances[self.current_node[0]][self.current_node[1]]

            adjacent_squares = self.get_adjacent_from(*self.current_node)
            self.visit_squares(self.pq, adjacent_squares, self.visited_nodes, self.distances, distance)

            squeeze_adjacent_squares = self.get_adjacent_from(*self.current_node, squeeze=True) - adjacent_squares

            if squeeze_adjacent_squares:
                self.visit_squares(self.pq, squeeze_adjacent_squares, self.visited_nodes, self.distances, distance, override_move_cost=2)

            if destination and self.current_node == destination:
                break

            self.visited_nodes.add(self.current_node)

            if not self.pq:
                break

            node_d, self.current_node = heapq.heappop(self.pq)
            if node_d == MAX_DISTANCE:
                return None

    def compute_path(self, source_x, source_y, destination_x, destination_y, available_movement_cost = None):
        self.build_structures(source_x, source_y)
        self.path((destination_x, destination_y))
        return self.backtrace(source_x, source_y, destination_x, destination_y, available_movement_cost=available_movement_cost)

    def incremental_path(self, source_x, source_y, destination_x, destination_y):
        rpath = self.backtrace(source_x, source_y, destination_x, destination_y, show_cost=True)
        if rpath and len(rpath) > 1:
            return rpath
        return None

    def visit_squares(self, pq, adjacent_squares, visited_nodes, distances, distance, override_move_cost=None):
        for node in adjacent_squares - visited_nodes:
            move_cost = override_move_cost if override_move_cost else (2 if self.map.difficult_terrain(self.entity, node[0], node[1], self.battle) else 1)
            if self.entity.prone():
                move_cost += 1
            current_distance = distance + move_cost
            if distances[node[0]][node[1]] > current_distance:
                distances[node[0]][node[1]] = current_distance
                heapq.heappush(pq, (current_distance, node))

    def get_adjacent_from(self, pos_x, pos_y, squeeze=False):
        valid_paths = set()
        for x_op in [-1, 0, 1]:
            for y_op in [-1, 0, 1]:
                cur_x = pos_x + x_op
                cur_y = pos_y + y_op

                if cur_x < 0 or cur_y < 0 or cur_x >= self.max_x or cur_y >= self.max_y:
                    continue
                if x_op == 0 and y_op == 0:
                    continue
                if self.map.passable(self.entity, cur_x, cur_y, self.battle, squeeze):
                    valid_paths.add((cur_x, cur_y))

        return valid_paths
