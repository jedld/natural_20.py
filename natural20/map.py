import yaml
from natural20.item_library.object import Object
from natural20.utils.static_light_builder import StaticLightBuilder
from natural20.entity import Entity
from natural20.utils.movement import requires_squeeze
from natural20.item_library.common import StoneWall, Ground, StoneWallDirectional
from natural20.item_library.door_object import DoorObject, DoorObjectWall
from natural20.item_library.pit_trap import PitTrap
from natural20.item_library.chest import Chest
from natural20.item_library.fireplace import Fireplace
from natural20.item_library.teleporter import Teleporter
from natural20.player_character import PlayerCharacter
from natural20.npc import Npc
from natural20.weapons import compute_max_weapon_range
from natural20.utils.list_utils import remove_duplicates, bresenham_line_of_sight
from natural20.utils.movement import Movement, compute_actual_moves
import math
import pdb
import os

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
    def __init__(self, session, map_file_path, name=None, properties=None):
        self.name = name
        self.session = session
        self.terrain = {}
        self.spawn_points = {}
        self.area_triggers = {}
        self.map = []
        if properties:
            self.properties = properties
        else:
            self.properties = self.load(map_file_path)
        base = self.properties.get('map', {}).get('base', [])

        self.size = [len(base[0]), len(base)]
        # print(f"map size: {self.size}")
        self.feet_per_grid = self.properties.get('grid_size', 5)
        self.base_map = []
        self.base_map_1 = []
        self.objects = []
        self.tokens = []
        self.unaware_npcs = []
        self.entities = {}  # Assuming entities is a dictionary
        self.interactable_objects = {}
        self.legend = self.properties.get('legend', {})
        self.linked_maps = {}

        for _ in range(self.size[0]):
            row = []
            for _ in range(self.size[1]):
                row.append(None)
            self.base_map.append(row)

        for _ in range(self.size[0]):
            row = []
            for _ in range(self.size[1]):
                row.append(None)
            self.base_map_1.append(row)

        for _ in range(self.size[0]):
            row = []
            for _ in range(self.size[1]):
                row.append([])
            self.objects.append(row)

        for _ in range(self.size[0]):
            row = []
            for _ in range(self.size[1]):
                row.append([])
            self.tokens.append(row)

        for cur_y, lines in enumerate(self.properties.get('map', {}).get('base', [])):
            for cur_x, c in enumerate(lines):
                if not c=='_':
                    self.base_map[cur_x][cur_y] = c

        for cur_y, lines in enumerate(self.properties.get('map', {}).get('base_1', [])):
            for cur_x, c in enumerate(lines):
                if not c=='.':
                    self.base_map_1[cur_x][cur_y] = c

        if self.properties.get('map', {}).get('meta'):
            self.meta_map = [[None for _ in range(self.size[1])] for _ in range(self.size[0])]

            for cur_y, lines in enumerate(self.properties.get('map', {}).get('meta')):
                for cur_x, c in enumerate(lines):
                    self.meta_map[cur_x][cur_y] = c
        else:
            self.meta_map = None

        self.light_builder = StaticLightBuilder(self)
        self.triggers = self.properties.get('triggers', {})
        self._compute_lights()
        self._setup_objects()
        self._setup_npcs()
        self._trigger_after_setup()

    def _compute_lights(self):
        self.light_map = self.light_builder.build_map()

    def _setup_objects(self):
        for pos_x in range(self.size[0]):
            for pos_y in range(self.size[1]):
                tokens = [self.base_map_1[pos_x][pos_y], self.base_map[pos_x][pos_y]]
                tokens = [token for token in tokens if token is not None]

                if not tokens:
                    continue

                for token in tokens:
                    if token == '#':
                        object_info = self.session.load_object('stone_wall')
                        obj = StoneWall(self, object_info)
                        self.interactable_objects[obj] = [pos_x, pos_y]
                        self.place_object(obj, pos_x, pos_y)
                    elif token == '?':
                        pass
                    elif token == '.':
                        object_info = self.session.load_object('ground')
                        obj = Ground(self, object_info)
                        self.place_object(obj, pos_x, pos_y)
                        self.interactable_objects[obj] = [pos_x, pos_y]
                    elif token == '-' or token == '|':
                        object_info = self.session.load_object('door')
                        obj = DoorObject(self, object_info, token)
                        self.interactable_objects[obj] = [pos_x, pos_y]
                        self.place_object(obj, pos_x, pos_y)
                    else:
                        object_meta = self.legend[token]
                        if object_meta is None:
                            raise Exception(f"unknown object token {token}")
                        if object_meta['type'] == 'mask':
                            continue
                        object_info = self.session.load_object(object_meta['type'])
                        self.place_object(object_info, pos_x, pos_y, object_meta)

    def _trigger_after_setup(self):
        for trigger_name, trigger in self.triggers.items():
            if trigger.get('type') == 'area':
                self.area_triggers[trigger_name] = trigger
        for row in self.objects:
            for objects in row:
                for obj in objects:
                    obj.after_setup()
    
    def _setup_npcs(self):
        for player in self.properties.get('player', []):
            column_index, row_index = player['position']
            overrides = player.get('overrides', {})
            player = PlayerCharacter.load(self.session, player['sheet'], override=overrides)
            self.add(player, column_index, row_index, group='a')

        for npc in self.properties.get('npc', []):
            npc_meta = npc
            column_index, row_index = npc['position']
            if not npc_meta['sub_type']:
                raise Exception('npc type requires sub_type as well')

            entity = self.session.npc(npc_meta['sub_type'], { "name" : npc_meta.get('name', None), "overrides" : npc_meta['overrides'], "rand_life" : True})

            self.add(entity, column_index, row_index, group=npc_meta.get('group', None))

        if self.meta_map:
            for column_index, meta_row in enumerate(self.meta_map):
                for row_index, token in enumerate(meta_row):
                    token_type = self.legend.get(token, {}).get('type')

                    if token_type == 'npc':
                        npc_meta = self.legend.get(token)
                        if not npc_meta['sub_type']:
                            raise Exception('npc type requires sub_type as well')

                        entity = self.session.npc(npc_meta['sub_type'], { "name" : npc_meta['name'], "overrides" : npc_meta.get('overrides', {}), "rand_life" : True })

                        self.add(entity, column_index, row_index, group=npc_meta.get('group', None))
                    elif token_type == 'spawn_point':
                        self.spawn_points[self.legend.get(token, {}).get('name')] = {
                            'location': [column_index, row_index]
                        }

    def add_linked_map(self, name, map):
        self.linked_maps[name] = map

    def entity_by_uid(self, uid):
        for entity in self.entities.keys():
            if entity.entity_uid == uid:
                return entity
        for entity in self.interactable_objects.keys():
            if str(entity.entity_uid) == uid:
                return entity
        return None
    
    def object_by_uid(self, uid):
        for obj in self.interactable_objects.keys():
            if str(obj.entity_uid) == uid:
                return obj
        return None

    def thing_at(self, pos_x, pos_y, reveal_concealed=False):
        if pos_x < 0 or pos_y < 0 or pos_x >= self.size[0] or pos_y >= self.size[1]:
            return []
        things = []
        things.append(self.entity_at(pos_x, pos_y))
        things.append(self.object_at(pos_x, pos_y, reveal_concealed=reveal_concealed))
        return [thing for thing in things if thing is not None]

    def add(self, entity, pos_x, pos_y, group='b'):
        self.unaware_npcs.append({'group': group if group else 'b', 'entity': entity})
        self.entities[entity] = [pos_x, pos_y]
        self.place((pos_x, pos_y), entity, None)

    def remove(self, entity, battle=None):
        pos_x, pos_y = self.entities.pop(entity)

        source_token_size = entity.token_size() - 1 if requires_squeeze(entity, pos_x, pos_y, self, battle) else entity.token_size()

        for ofs_x in range(source_token_size):
            for ofs_y in range(source_token_size):
                self.tokens[pos_x + ofs_x][pos_y + ofs_y] = None

    def load(self, map_file_path):
        # Add .yml extension if not present
        if not map_file_path.endswith('.yml'):
            map_file_path += '.yml'
        if not os.path.exists(map_file_path):
            map_file_path = os.path.join(self.session.root_path, map_file_path)
        # print("loading map file: ", map_file_path)
        with open(map_file_path, 'r') as file:
            data = yaml.safe_load(file)
            return data

    def movement_cost(self, entity, path, battle=None, manual_jump=None):
        if not path:
            return Movement.empty()

        budget = entity.available_movement(battle) / self.feet_per_grid
        return compute_actual_moves(entity, path, self, battle, budget, test_placement=False, manual_jump=manual_jump)

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

        for obj in self.objects_at(pos_x, pos_y):
            if obj != entity:
                obj.on_enter(entity, self, battle)

    def place_at_spawn_point(self, position, entity, token=None, battle=None):
        if str(position) not in self.spawn_points:
            raise Exception(f"unknown spawn position {position}. should be any of {','.join(self.spawn_points.keys())}")

        pos_x, pos_y = self.spawn_points[str(position)]['location']
        self.place((pos_x, pos_y), entity, token, battle)
        print(f"place {entity.name} at {pos_x}, {pos_y}")

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

    def objects_near(self, entity, battle=None):
        target_squares = entity.melee_squares(self)
        target_squares += self.entity_squares(entity)
        objects = []

        available_objects = []
        for square in target_squares:
            available_objects.extend(self.objects_at(square[0], square[1]))
            nearby_entity = self.entity_at(square[0], square[1])
            if nearby_entity and nearby_entity!=entity:
                available_objects.append(nearby_entity)

        for obj in available_objects:
            if hasattr(obj,'available_interactions') and obj.available_interactions(entity, battle):
                objects.append(obj)

        return objects

    def place_object(self, object_info, pos_x, pos_y, object_meta=None):
        # print(f"placing object {object_info} at {pos_x}, {pos_y}")
        if object_meta is None:
            object_meta = {}
        if object_info is None:
            return

        if isinstance(object_info, Object):
            obj = object_info
        elif object_info.get('item_class'):
            item_klass = globals()[object_info['item_class']]
            object_info = object_info.copy()
            object_info.update(object_meta)

            item_obj = item_klass(self, object_info)
            if 'ItemLibrary.AreaTrigger' in item_klass.__module__:
                self.area_triggers[item_obj] = {}
            obj = item_obj
        else:
            object_meta.update(object_info)
            obj = Object(self, object_meta)

        self.interactable_objects[obj] = [pos_x, pos_y]

        if isinstance(obj.token, list):
            for y, line in enumerate(obj.token):
                for x, t in enumerate(line):
                    if t == '.':
                        continue
                    self.objects[pos_x + x][pos_y + y].append(obj)
        else:
            self.objects[pos_x][pos_y].append(obj)

        return obj

    def is_heavily_obscured(self, entity, pos_override=None):
        return self.light_at_entity(entity, pos_override) < 0.5

    def hiding_spots_for(self, entity, battle=None):
        hiding_spots = []
        for pos_x in range(self.size[0]):
            for pos_y in range(self.size[1]):
                if self.line_of_sight(pos_x, pos_y, *self.entities[entity]) is None:
                    continue
                if not self.placeable(entity, pos_x, pos_y):
                    continue
                if self.can_hide(entity, [pos_x, pos_y], battle)[0]:
                    hiding_spots.append([pos_x, pos_y])
        return hiding_spots

    def can_hide(self, entity, pos_override=None, battle=None):
        if pos_override is not None:
            entity_squares = self.entity_squares_at_pos(entity, pos_override[0], pos_override[1])
        else:
            entity_squares = self.entity_squares(entity)

        behind_cover = False
        heavily_obscured = False

        opponents = []
        if battle:
            opponents = [opp for opp in battle.opponents_of(entity) if opp.conscious()]

        opponent_line_of_sight = False

        for opp in opponents:
            if self.can_see(opp, entity, distance=None, entity_1_pos=None, entity_2_pos=pos_override, heavy_cover=True):
                opponent_line_of_sight = True
                break

        # check if behind cover
        for pos in entity_squares:
            pos_x, pos_y = pos
            for i in range(-1, 2):
                for j in range(-1, 2):
                    if i == 0 and j == 0:
                        continue

                    things = self.thing_at(pos_x + i, pos_y + j)
                    for thing in things:
                        if thing == entity:
                            continue

                        if isinstance(thing, Object):
                            if thing.three_quarter_cover() or thing.total_cover():
                                behind_cover = True
                                break
                        if isinstance(thing, Entity) and entity.class_feature('naturally_stealthy'):
                            if entity.size_identifier() < thing.size_identifier():
                                behind_cover = True
                                break

        hide_failed_reasons = []

        if self.is_heavily_obscured(entity, pos_override=pos_override):
            heavily_obscured = True

        if not behind_cover and not heavily_obscured:
            hide_failed_reasons.append("not behind cover or heavily obscured")

        if opponent_line_of_sight:
            hide_failed_reasons.append("opponent can see entity")

        return len(hide_failed_reasons) == 0, hide_failed_reasons


    def valid_targets_for(self, entity, action, target_types=None, range=None, active_perception=None, include_objects=False, filter=None):
        if target_types is None:
            target_types = ['enemies']

        attack_range = compute_max_weapon_range(self.session, action, range)

        if attack_range is None:
            raise ValueError('attack range cannot be None')

        targets = [k for k, pos in self.entities.items() if not k.dead() and k.hp() is not None and self.distance(k, entity) * self.feet_per_grid <= attack_range and (filter is None or k.eval_if(filter))]

        if include_objects:
            targets += [obj for obj, _position in self.interactable_objects.items() if not obj.dead() and ('ignore_los' in target_types or self.can_see(entity, obj, active_perception=active_perception)) and self.distance(obj, entity) * self.feet_per_grid <= attack_range and (filter is None or obj.eval_if(filter))]

        return targets

    def difficult_terrain(self, entity, pos_x, pos_y, battle=None):
        if entity is None:
            return False

        for pos in self.entity_squares_at_pos(entity, pos_x, pos_y):
            r_x, r_y = pos
            if self.tokens[r_x][r_y] and self.tokens[r_x][r_y]['entity'] == entity:
                continue
            if self.tokens[r_x][r_y] and not self.tokens[r_x][r_y]['entity'].dead():
                return True
            if self.object_at(r_x, r_y) and self.object_at(r_x, r_y).movement_cost() > 1:
                return True

        return False

    def wall(self, pos_x, pos_y):
        if pos_x < 0 or pos_y < 0:
            return True
        if pos_x >= self.size[0] or pos_y >= self.size[1]:
            return True
        if self.object_at(pos_x, pos_y) and self.object_at(pos_x, pos_y).wall():
            return True
        return False

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
                # print(f"{entity.name} cannot see {k.name}")
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
            if not entity:
                raise ValueError('invalid entity')
            if not self.entities.get(entity):
                # might be a deepcopied object so we try with the uid
                _entity = self.entity_by_uid(entity.entity_uid)
                if not _entity:
                    raise ValueError(f'entity {entity} not found')
                return self.entities[_entity]
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
    
    def can_see_square(self, entity, pos2: tuple, allow_dark_vision=True):
        has_line_of_sight = False
        max_illumination = 0.0
        sighting_distance = None
        pos2_x, pos2_y = pos2
        entity_1_squares = self.entity_squares(entity)
        for pos1 in entity_1_squares:
            pos1_x, pos1_y = pos1
            if [pos1_x, pos1_y] == [pos2_x, pos2_y]:
                return True

            # for ascii map rendering we don't want to hide the walls themselves
            # so that the user is aware of the walls otherwise it will just 
            # look like an empty space. For web rendering we don't need to do this
            # since we have the map as an image background and the walls are visible
            inclusive = not self.session.render_for_text

            if self.line_of_sight(pos1_x, pos1_y, pos2_x, pos2_y, inclusive=inclusive) is None:
                continue

            location_illumination = self.light_at(pos2_x, pos2_y)
            max_illumination = max(location_illumination, max_illumination)
            sighting_distance = math.floor(math.sqrt((pos1_x - pos2_x)**2 + (pos1_y - pos2_y)**2))
            has_line_of_sight = True

        if has_line_of_sight and max_illumination < 0.5:
            return allow_dark_vision and entity.darkvision(sighting_distance * self.feet_per_grid)

        return has_line_of_sight

    def can_see(self, entity, entity2, distance=None, entity_1_pos=None, entity_2_pos=None, \
                allow_dark_vision=True, active_perception=0, active_perception_disadvantage=0,\
                creature_size_min=None, heavy_cover=False):
        """
        Check if entity can see entity2
        """
        if entity == entity2:
            return True

        if entity not in self.entities and entity not in self.interactable_objects:
            return False

        if entity2.hidden():
            if entity.passive_perception() < entity2.hidden_stealth:
                return False
            if active_perception < entity2.hidden_stealth:
                return False

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
                    # print(f"pos1_x {pos1_x} pos1_y {pos1_y} size {self.size}")
                    continue
                if pos2_x >= self.size[0] or pos2_x < 0 or pos2_y >= self.size[1] or pos2_y < 0:
                    # print(f"pos2_x {pos2_x} pos2_y {pos2_y} size {self.size}")
                    continue
                line_of_sight_info = self.line_of_sight(pos1_x, pos1_y, pos2_x, pos2_y, distance=distance, \
                                                        inclusive=True, heavy_cover=heavy_cover,
                                                        creature_size_min=creature_size_min)
                if line_of_sight_info is None:
                    # print(f"no line of sight from {pos1_x},{pos1_y} to {pos2_x},{pos2_y} {distance}")
                    continue

                location_illumination = self.light_at(pos2_x, pos2_y)
                # print(f"location_illumination {location_illumination}")
                max_illumination = max(location_illumination, max_illumination)
                sighting_distance = math.floor(math.sqrt((pos1_x - pos2_x)**2 + (pos1_y - pos2_y)**2))
                has_line_of_sight = True

        if not has_line_of_sight:
            return False

        if allow_dark_vision and entity.darkvision(sighting_distance * self.feet_per_grid):
            max_illumination += 0.5

        if max_illumination == 0.0:
            has_line_of_sight = False

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
    
    def bidirectionally_passable(self, entity, pos_x, pos_y, origin, battle=None, allow_squeeze=True, ignore_opposing=False):
        incorporeal = entity.class_feature('incorporeal_movement')
        if self.passable(entity, pos_x, pos_y, battle, allow_squeeze, origin=origin, ignore_opposing=ignore_opposing, incorporeal=incorporeal) and \
            self.passable(entity, *origin, battle, allow_squeeze, origin=(pos_x, pos_y), ignore_opposing=ignore_opposing, incorporeal=incorporeal):
            return True

    def passable(self, entity, pos_x, pos_y, battle=None, allow_squeeze=True, origin=None, ignore_opposing=False,
                 incorporeal=False):
        effective_token_size = entity.token_size() - 1 if allow_squeeze and entity.token_size() > 1 else entity.token_size()
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

                for object in self.objects_at(relative_x, relative_y):
                    if not object.passable(origin) and not incorporeal:
                        return False

                if battle and self.tokens[relative_x][relative_y]:
                    location_entity = self.tokens[relative_x][relative_y]['entity']

                    if self.tokens[relative_x][relative_y]['entity'] == entity:
                        continue
                    if not battle.opposing(location_entity, entity):
                        continue
                    if location_entity.incapacitated():
                        continue
                    if entity.class_feature('halfling_nimbleness') and (location_entity.size_identifier() - entity.size_identifier()) >= 1:
                        continue
                    if not ignore_opposing and battle.opposing(location_entity, entity) and abs(location_entity.size_identifier() - entity.size_identifier()) < 2:
                        return False

        return True
    
    def placeable(self, entity, pos_x, pos_y, battle=None, squeeze=True):
        if not self.passable(entity, pos_x, pos_y, battle, squeeze):
            return False

        for pos in self.entity_squares_at_pos(entity, pos_x, pos_y, squeeze):
            p_x, p_y = pos
            if self.tokens[p_x][p_y] and self.tokens[p_x][p_y]['entity'] == entity:
                continue
            if self.tokens[p_x][p_y]:
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
            return self.entities.get(thing, None)
        
    def line_of_sight(self, pos1_x, pos1_y, pos2_x, pos2_y, distance=None, \
                      inclusive=False, heavy_cover=False, entity=False, log_path=False,\
                        creature_size_min=None):
        squares = self.squares_in_path(pos1_x, pos1_y, pos2_x, pos2_y, inclusive=inclusive)
        squares_results = []
        prev_square = [pos1_x, pos1_y]
        for index, s in enumerate(squares):
            if log_path:
                self.base_map[s[1]][s[0]] = 'H'

            if distance and index == (distance - 1):
                return None

            if self.opaque(*s, origin=prev_square) or self.opaque(*prev_square, origin=s):
                return None

            if self.cover_at(*s) == 'total':
                return None

            if heavy_cover and self.cover_at(*s) == 'three_quarter':
                return None
            if creature_size_min and self.entity_at(*s) and self.entity_at(*s).size_identifier() >= creature_size_min:
                return None

            prev_square = s

            squares_results.append([self.cover_at(*s, entity), s])
        return squares_results


    def light_in_sight(self, pos1_x, pos1_y, pos2_x, pos2_y, min_distance=None, distance=None, inclusive=True, entity=False):
        squares = self.squares_in_path(pos2_x, pos2_y, pos1_x, pos1_y, inclusive=inclusive)
        min_distance_reached = True
        prev = [pos2_x, pos2_y]
        for index, s in enumerate(squares):
            if min_distance and index > min_distance:
                min_distance_reached = False
            if distance and index > distance:
                return [False, False]
            if self.opaque(*s, prev) or self.opaque(*prev, s):
                return [False, False]
            if self.cover_at(*s) == 'total':
                return [False, False]
            prev = s

        return [min_distance_reached, True]

    def opaque(self, pos_x, pos_y, origin=None):
        if pos_x < 0 or pos_y < 0 or pos_x >= self.size[0] or pos_y >= self.size[1]:
            raise ValueError(f"Invalid position: {pos_x},{pos_y} should not exceed (0 - {self.size[0]- 1 }),(0 - {self.size[1] - 1})")

        if self.base_map[pos_x][pos_y] == '#':
            return True
        else:
            if self.object_at(pos_x, pos_y):
                for object in self.objects_at(pos_x, pos_y):
                    if object.opaque(origin):
                        return True
            else:
                if origin:
                    if self.object_at(*origin):
                        for object in self.objects_at(*origin):
                            if object.opaque((pos_x, pos_y)):
                                return True

                return None

    def squares_in_path(self, pos1_x, pos1_y, pos2_x, pos2_y, distance=None, inclusive=True):
        if [pos1_x, pos1_y] == [pos2_x, pos2_y]:
            return [(pos1_x, pos1_y)] if inclusive else []

        arrs = bresenham_line_of_sight(pos1_x, pos1_y, pos2_x, pos2_y)

        if inclusive and arrs[-1] != (pos2_x, pos2_y):
            arrs.append((pos2_x, pos2_y))
        
        if not inclusive and arrs[-1] == (pos2_x, pos2_y):
            arrs.pop()

        return remove_duplicates(arrs)

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
            return self.light_map[pos_x][pos_y] + self.light_builder.light_at(pos_x, pos_y)
        else:
            return self.light_builder.light_at(pos_x, pos_y)

    def light_at_entity(self, entity, pos_override=None):
        intensities = []
        if pos_override:
            entity_squares = self.entity_squares_at_pos(entity, *pos_override)
        else:
            entity_squares = self.entity_squares(entity)

        for entity_square in entity_squares:
            pos_x, pos_y = entity_square
            intensities.append(self.light_at(pos_x, pos_y))
        return max(intensities)


    def entities_in_range(self, entity, range):
        entities = []
        for entity2, _position in self.entities.items():
            if entity == entity2:
                continue
            if entity.dead():
                continue
            if self.distance(entity, entity2) * self.feet_per_grid <= range:
                entities.append(entity2)
        return entities

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


    def activate_map_triggers(self, trigger_type, source, opt=None):
        if opt is None:
            opt = {}
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

    def items_on_the_ground(self, entity):
        target_squares = entity.melee_squares(self)
        target_squares += self.entity_squares(entity)

        available_objects = [obj for square in target_squares for obj in self.objects_at(*square) if obj]

        ground_objects = [obj for obj in available_objects if isinstance(obj, Ground)]
        result = []
        for obj in ground_objects:
            items = [name for name, meta in obj.inventory.items() if meta['qty'] > 0]
            if items:
                result.append((obj, items))

        return result

    @staticmethod
    def from_dict(session, data):
        entity_hash = {}

        battle_map = Map(session, None, properties=data['map']['properties'])
        battle_map.entities = {}
        for uid, entity_and_pos in data['entities'].items():
            entity, pos = entity_and_pos
            if entity['type']=='pc':
                entity['entity_uid'] = uid
                player_character = PlayerCharacter(session, entity['properties'], name=entity['name'])
                player_character.attributes = entity['attributes']
                battle_map.entities[player_character] = pos
                entity_hash[uid] = player_character
            elif entity['type']=='npc':
                entity['entity_uid'] = uid
                npc = Npc(session, entity['npc_type'], { "name" : entity['name']})
                npc.properties = entity['properties']
                npc.attributes = entity['attributes']
                npc.inventory = entity['inventory']
                battle_map.entities[npc] = pos
                entity_hash[uid] = npc

        map_data = data['map']

        # reset tokens
        for x in range(battle_map.size[0]):
            for y in range(battle_map.size[1]):
                battle_map.tokens[x][y] = None

        for token in map_data['tokens']:
            entity = entity_hash[token['entity']]
            battle_map.place((token['x'], token['y']), entity)

        return battle_map


    def to_dict(self)->dict:
        entity_hash = {}
        for entity, pos in self.entities.items():
            entity_hash[entity.entity_uid] = [
                entity.to_dict(),
                pos
            ]
        map_hash = {
                'name': self.name,
                'size': self.size,
                'feet_per_grid': self.feet_per_grid,
                'legend': self.legend,
                'properties': self.properties
        }

        tokens = []
        for x in range(self.size[0]):
            for y in range(self.size[1]):
                if self.tokens[x][y]:
                    token = {
                        'x': x,
                        'y': y,
                        'entity': self.tokens[x][y]['entity'].entity_uid,
                        'token': self.tokens[x][y]['token']
                    }
                    tokens.append(token)
        map_hash['tokens'] = tokens

        return {
            'entities' : entity_hash,
            'map': map_hash
        }
