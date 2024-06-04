import yaml
from natural20.item_library.object import Object
from natural20.utils.static_light_builder import StaticLightBuilder
from natural20.entity import Entity
from natural20.utils.movement import requires_squeeze
import math
import pdb

class Terrain():
    def __init__(self, name, passable, movement_cost, symbol=None):
        self.name = name
        self.passable = passable
        self.movement_cost = movement_cost
        
        self.symbol = symbol if symbol else name[0].upper()

    def symbol(self):
        return self.symbol

def dirt():
    return Terrain("dirt", True, 1.0)

class Map():
    def __init__(self, map_file_path):
        self.terrain = {}
        self.area_triggers = {}
        self.map = []
        self.properties = self.load(map_file_path)
        base = self.properties.get('map', {}).get('base', [])
        
        self.size = [len(base[0]), len(base)]
        print(f"map size: {self.size}")
        self.feet_per_grid = self.properties.get('grid_size', 5)
        self.base_map = []
        self.objects = []
        self.tokens = []
        self.entities = {}  # Assuming entities is a dictionary
        
        for _ in range(self.size[1]):
            row = []
            for _ in range(self.size[0]):
                row.append(None)
            self.base_map.append(row)

        for _ in range(self.size[1]):
            row = []
            for _ in range(self.size[0]):
                row.append([])
            self.objects.append(row)

        for _ in range(self.size[1]):
            row = []
            for _ in range(self.size[0]):
                row.append([])
            self.tokens.append(row)

        for cur_y, lines in enumerate(self.properties.get('map', {}).get('base', [])):
            for cur_x, c in enumerate(lines):
                if not c=='.':
                    self.base_map[cur_x][cur_y] = c

        self.light_builder = StaticLightBuilder(self)
        self.triggers = self.properties.get('triggers', {})
        self._compute_lights()

    def _compute_lights(self):
        self.light_map = self.light_builder.build_map()



    def load(self, map_file_path):
        with open(map_file_path, 'r') as file:
            data = yaml.safe_load(file)
            return data
        
    def move_to(self, entity: Entity, pos_x, pos_y, battle):
        cur_x, cur_y = self.entities[entity]

        entity_data = self.tokens[cur_x][cur_y]

        source_token_size = entity.token_size() - 1 if requires_squeeze(entity, cur_x, cur_y, self, battle) else entity.token_size()

        if requires_squeeze(entity, pos_x, pos_y, self, battle):
            entity.squeezed()
            destination_token_size = entity.token_size() - 1
        else:
            entity.unsqueeze()
            destination_token_size = entity.token_size()

        for ofs_x in range(source_token_size):
            for ofs_y in range(source_token_size):
                self.tokens[cur_x + ofs_x][cur_y + ofs_y] = None

        for ofs_x in range(destination_token_size):
            for ofs_y in range(destination_token_size):
                self.tokens[pos_x + ofs_x][pos_y + ofs_y] = entity_data

        self.entities[entity] = [pos_x, pos_y]

    def place(self, position, entity, token=None, battle=None):
        pos_x, pos_y = position

        if entity is None:
            raise ValueError('entity param is required')
        
        if pos_x < 0 or pos_y < 0 or pos_x >= self.size[0] or pos_y >= self.size[1]:
            raise ValueError(f"Invalid position: {pos_x},{pos_y} should not exceed (0 - {self.size[0]- 1 }),(0 - {self.size[1] - 1})")

        entity_data = {'entity': entity, 'token': token or entity.name}
        self.tokens[pos_x][pos_y] = entity_data
        self.entities[entity] = [pos_x, pos_y]

        source_token_size = entity.token_size()

        for ofs_x in range(source_token_size):
            for ofs_y in range(source_token_size):
                self.tokens[pos_x + ofs_x][pos_y + ofs_y] = entity_data

    def object_at(self, pos_x, pos_y, reveal_concealed=False):
        objects_at_position = self.objects[pos_x][pos_y]
        for obj in objects_at_position:
            if reveal_concealed or not obj.concealed():
                return obj
        return None
    
    # Get object at map location
    # @param pos_x [Integer]
    # @param pos_y [Integer]
    # @return [List[Object]]
    def objects_at(self, pos_x, pos_y):
        return self.objects[pos_x][pos_y]
    
    # Natural20::Entity to look around
    # @param entity [Natural20::Entity] The entity to look around his line of sight
    # @return [Hash] entities in line of sight
    def look(self, entity, distance=None):
        visible_entities = {}
        for k, v in self.entities.items():
            if k == entity:
                continue

            pos1_x, pos1_y = v

            if not self.can_see(entity, k, distance=distance):
                print(f"{entity.name} cannot see {k.name}")
                continue

            visible_entities[k] = [pos1_x, pos1_y]

        return visible_entities

    def jump_required(self, entity, pos_x, pos_y):
        for pos in self.entity_squares_at_pos(entity, pos_x, pos_y):
            r_x, r_y = pos
            if self.tokens[r_x][r_y] and self.tokens[r_x][r_y]['entity'] == entity:
                continue
            if self.object_at(r_x, r_y) and self.object_at(r_x, r_y).jump_required() and not entity.flying():
                return True
        return False
    
    # Get entity at map location
    # @param pos_x [Integer]
    # @param pos_y [Integer]
    # @return [Natural20::Entity]
    def entity_at(self, pos_x, pos_y):
        if pos_x < 0 or pos_y < 0 or pos_x >= self.size[0] or pos_y >= self.size[1]:
            return None
        
        entity_data = self.tokens[pos_x][pos_y]
        if entity_data is None or len(entity_data) == 0:
            return None

        return entity_data['entity']
    
    def position_of(self, entity):
        if isinstance(entity, Object):
            return self.interactable_objects[entity]
        else:
            return self.entities[entity]

    def entity_squares_at_pos(self, entity, pos1_x, pos1_y, squeeze=False):
        entity_1_squares = []
        token_size = entity.token_size() - 1 if squeeze else entity.token_size()
        for ofs_x in range(token_size):
            for ofs_y in range(token_size):
                if pos1_x + ofs_x >= self.size[0] or pos1_y + ofs_y >= self.size[1]:
                    continue

                entity_1_squares.append([pos1_x + ofs_x, pos1_y + ofs_y])
        return entity_1_squares

    def can_see_square(self, entity, pos2_x, pos2_y, allow_dark_vision=True):
        has_line_of_sight = False
        max_illumination = 0.0
        sighting_distance = None

        entity_1_squares = self.entity_squares(entity)
        for pos1 in entity_1_squares:
            pos1_x, pos1_y = pos1
            if [pos1_x, pos1_y] == [pos2_x, pos2_y]:
                return True
            if not self.line_of_sight(pos1_x, pos1_y, pos2_x, pos2_y, inclusive=False):
                continue

            location_illumination = self.light_at(pos2_x, pos2_y)
            max_illumination = max(location_illumination, max_illumination)
            sighting_distance = math.floor(math.sqrt((pos1_x - pos2_x)**2 + (pos1_y - pos2_y)**2))
            has_line_of_sight = True

        if has_line_of_sight and max_illumination < 0.5:
            return allow_dark_vision and entity.darkvision(sighting_distance * self.feet_per_grid)

        return has_line_of_sight

    def can_see(self, entity, entity2, distance=None, entity_1_pos=None, entity_2_pos=None, allow_dark_vision=True, active_perception=0, active_perception_disadvantage=0):
        if entity not in self.entities and entity not in self.interactable_objects:
            print(self.entities)
            raise ValueError('Invalid entity passed')

        entity_1_squares = self.entity_squares_at_pos(entity, *entity_1_pos) if entity_1_pos else self.entity_squares(entity)
        entity_2_squares = self.entity_squares_at_pos(entity2, *entity_2_pos) if entity_2_pos else self.entity_squares(entity2)

        has_line_of_sight = False
        max_illumination = 0.0
        sighting_distance = None
        # print(f"entity_1_squares {entity_1_squares}")
        # print(f"entity_2_squares {entity_2_squares}")
        for pos1 in entity_1_squares:
            for pos2 in entity_2_squares:
                pos1_x, pos1_y = pos1
                pos2_x, pos2_y = pos2
                if pos1_x >= self.size[0] or pos1_x < 0 or pos1_y >= self.size[1] or pos1_y < 0:
                    print(f"pos1_x {pos1_x} pos1_y {pos1_y} size {self.size}")
                    continue
                if pos2_x >= self.size[0] or pos2_x < 0 or pos2_y >= self.size[1] or pos2_y < 0:
                    print(f"pos2_x {pos2_x} pos2_y {pos2_y} size {self.size}")
                    continue
                line_of_sight_info = self.line_of_sight(pos1_x, pos1_y, pos2_x, pos2_y, distance=distance)
                if line_of_sight_info==None:
                    print(f"no line of sight from {pos1_x},{pos1_y} to {pos2_x},{pos2_y} {distance}")
                    continue

                location_illumination = self.light_at(pos2_x, pos2_y)
                # print(f"location_illumination {location_illumination}")
                max_illumination = max(location_illumination, max_illumination)
                sighting_distance = math.floor(math.sqrt((pos1_x - pos2_x)**2 + (pos1_y - pos2_y)**2))
                has_line_of_sight = True

        if has_line_of_sight and max_illumination < 0.5:
            has_line_of_sight =  allow_dark_vision and entity.darkvision(sighting_distance * self.feet_per_grid)
        
        if not has_line_of_sight:
            pdb.set_trace()
        return has_line_of_sight

    def entity_squares(self, entity, squeeze=False):
        if not entity:
            raise ValueError('invalid entity')

        pos1_x, pos1_y = self.entity_or_object_pos(entity)
        entity_1_squares = []
        token_size = entity.token_size() - 1 if squeeze else entity.token_size()
        for ofs_x in range(token_size):
            for ofs_y in range(token_size):
                if pos1_x + ofs_x >= self.size[0] or pos1_y + ofs_y >= self.size[1]:
                    continue

                entity_1_squares.append([pos1_x + ofs_x, pos1_y + ofs_y])
        return entity_1_squares
    
    def passable(self, entity, pos_x, pos_y, battle=None, allow_squeeze=True):
        effective_token_size = entity.token_size() - 1 if allow_squeeze else entity.token_size()
        for ofs_x in range(effective_token_size):
            for ofs_y in range(effective_token_size):
                relative_x = pos_x + ofs_x
                relative_y = pos_y + ofs_y

                if relative_x < 0:
                    return False
                if relative_y < 0:
                    return False
                if relative_x >= self.size[0]:
                    return False
                if relative_y >= self.size[1]:
                    return False
                if self.base_map[relative_x][relative_y] == '#':
                    return False
                if self.object_at(relative_x, relative_y) and not self.object_at(relative_x, relative_y).passable():
                    return False

                if battle and self.tokens[relative_x][relative_y]:
                    location_entity = self.tokens[relative_x][relative_y]['entity']

                    if self.tokens[relative_x][relative_y]['entity'] == entity:
                        continue
                    if not battle.opposing(location_entity, entity):
                        continue
                    if location_entity.dead() or location_entity.unconscious():
                        continue
                    if entity.class_feature('halfling_nimbleness') and (location_entity.size_identifier() - entity.size_identifier()) >= 1:
                        continue
                    if battle.opposing(location_entity, entity) and abs(location_entity.size_identifier() - entity.size_identifier()) < 2:
                        return False

        return True
    
    def placeable(self, entity, pos_x, pos_y, battle=None, squeeze=True):
        if not self.passable(entity, pos_x, pos_y, battle, squeeze):
            return False

        for pos in self.entity_squares_at_pos(entity, pos_x, pos_y, squeeze):
            p_x, p_y = pos
            if self.tokens[p_x][p_y] and self.tokens[p_x][p_y]['entity'] == entity:
                continue
            if self.tokens[p_x][p_y] and not self.tokens[p_x][p_y]['entity'].dead():
                return False
            if self.object_at(p_x, p_y) and not self.object_at(p_x, p_y).passable():
                return False
            if self.object_at(p_x, p_y) and not self.object_at(p_x, p_y).placeable():
                return False

        return True

    def entity_or_object_pos(self, thing):
        if isinstance(thing, Object):
            return self.interactable_objects[thing]
        else:
            return self.entities[thing]
        
    def line_of_sight(self, pos1_x, pos1_y, pos2_x, pos2_y, distance=None, inclusive=False, entity=False):
        squares = self.squares_in_path(pos1_x, pos1_y, pos2_x, pos2_y, inclusive=inclusive)
        squares_results = []
        for index, s in enumerate(squares):
            if distance and index == (distance - 1):
                return None
            if self.opaque(*s):
                return None
            if self.cover_at(*s) == 'total':
                return None

            squares_results.append([self.cover_at(*s, entity), s])
        return squares_results
        
    def opaque(self, pos_x, pos_y):
        if self.base_map[pos_x][pos_y] == '#':
            return True
        elif self.base_map[pos_x][pos_y] == '.':
            return False
        else:
            return self.object_at(pos_x, pos_y).opaque() if self.object_at(pos_x, pos_y) else None


    def squares_in_path(self, pos1_x, pos1_y, pos2_x, pos2_y, distance=None, inclusive=True):
        if [pos1_x, pos1_y] == [pos2_x, pos2_y]:
            return [[pos1_x, pos1_y]] if inclusive else []

        arrs = []
        if pos2_x == pos1_x:
            scanner = range(pos1_y, pos2_y + 1) if pos2_y > pos1_y else range(pos2_y, pos1_y + 1)

            for index, y in enumerate(scanner):
                if distance is not None and index >= distance:
                    break
                if not inclusive and (y == pos1_y or y == pos2_y):
                    continue

                arrs.append([pos1_x, y])
        else:
            m = (pos2_y - pos1_y) / (pos2_x - pos1_x)
            scanner = range(pos1_x, pos2_x + 1) if pos2_x > pos1_x else range(pos2_x, pos1_x + 1)
            if m == 0:
                for index, x in enumerate(scanner):
                    if distance is not None and index >= distance:
                        break
                    if not inclusive and (x == pos1_x or x == pos2_x):
                        continue

                    arrs.append([x, pos2_y])
            else:
                b = pos1_y - m * pos1_x
                step = 1 / abs(m) if abs(m) > 1 else abs(m)

                for index, x in enumerate(scanner):
                    y = round(m * x + b)

                    if distance is not None and index >= distance:
                        break
                    if not inclusive and ((round(x) == pos1_x and y == pos1_y) or (round(x) == pos2_x and y == pos2_y)):
                        continue

                    arrs.append([round(x), y])

        return list(set(map(tuple, arrs)))

    def cover_at(self, pos_x, pos_y, entity=False):
        if self.object_at(pos_x, pos_y) and self.object_at(pos_x, pos_y).half_cover():
            return 'half'
        elif self.object_at(pos_x, pos_y) and self.object_at(pos_x, pos_y).three_quarter_cover():
            return 'three_quarter'
        elif self.object_at(pos_x, pos_y) and self.object_at(pos_x, pos_y).total_cover():
            return 'total'
        elif entity and self.entity_at(pos_x, pos_y):
            return self.entity_at(pos_x, pos_y).size_identifier()
        else:
            return 'none'


    def light_at(self, pos_x, pos_y):
        if self.light_map is not None:
            if self.light_map[pos_x][pos_y] >= 1.0:
                return self.light_map[pos_x][pos_y]

            return self.light_map[pos_x][pos_y] + self.light_builder.light_at(pos_x, pos_y)
        else:
            return self.light_builder.light_at(pos_x, pos_y)


    def distance(self, entity1, entity2, entity_1_pos=None, entity_2_pos=None):
        if entity1 is None:
            raise ValueError('entity 1 param cannot be None')
        if entity2 is None:
            raise ValueError('entity 2 param cannot be None')

        # entity 1 squares
        entity_1_sq = self.entity_squares_at_pos(entity1, *entity_1_pos) if entity_1_pos else self.entity_squares(entity1)
        entity_2_sq = self.entity_squares_at_pos(entity2, *entity_2_pos) if entity_2_pos else self.entity_squares(entity2)

        distances = []
        for ent1_pos in entity_1_sq:
            for ent2_pos in entity_2_sq:
                pos1_x, pos1_y = ent1_pos
                pos2_x, pos2_y = ent2_pos
                distances.append(int(((pos1_x - pos2_x) ** 2 + (pos1_y - pos2_y) ** 2) ** 0.5))

        return min(distances)


    def area_trigger(self, entity, position, is_flying):
        trigger_results = [k.area_trigger_handler(entity, position, is_flying) for k, _prop in self.area_triggers.items() if not k.dead()]
        trigger_results = [result for result in trigger_results if result is not None]
        trigger_results = list(set(trigger_results))
        return trigger_results


    def activate_map_triggers(self, trigger_type, source, opt={}):
        if trigger_type in self.triggers:
            for trigger in self.triggers[trigger_type]:
                if trigger.get('if') and not source.eval_if(trigger.get('if'), opt):
                    continue

                if trigger['type'] == 'message':
                    opt.get('ui_controller').show_message(trigger['content'])
                elif trigger['type'] == 'battle_end':
                    return 'battle_end'
                else:
                    raise ValueError(f"unknown trigger type {trigger['type']}")
