import numpy as np
import pdb
from natural20.map import Map
from natural20.battle import Battle
from natural20.item_library.door_object import DoorObject, DoorObjectWall
from natural20.item_library.teleporter import Teleporter
from natural20.item_library.chasm import Chasm
from natural20.spell.objects.grease_surface import GreaseSurface
import logging
class JsonRenderer:
    def __init__(self, map: Map, battle: Battle=None, padding=None, logger=None):
        self.map = map
        self.battle = battle
        self.padding = padding
        if logger is None:
            self.logger = logging.getLogger(__name__)
        else:
            self.logger = logger

    def _team_visuals_for(self, entity):
        web_extensions = (self.map.properties.get('extensions') or {}).get('web') or {}
        team_border_tints = web_extensions.get('team_border_tints') or {}
        if not team_border_tints:
            return None, None

        group = None
        if self.battle and hasattr(self.battle, 'entities') and entity in self.battle.entities:
            try:
                group = self.battle.entity_group_for(entity)
            except Exception:
                group = None

        if group is None:
            group = getattr(entity, 'group', None)

        tint = team_border_tints.get(group)
        if not tint:
            return None, None

        return group, tint

    def render(self, entity_pov=None, path=None, select_pos=None):
        if path is None:
           path = []
        result = []
        entity_pov_locations = None
        width, height = self.map.size

        # Per-render memoization for Map.light_at (called up to 9x per tile via
        # the soft-shadow neighbor loop).
        _map_light_at = self.map.light_at
        _light_cache = {}
        def light_at(x, y):
            key = (x, y)
            v = _light_cache.get(key)
            if v is None:
                v = _map_light_at(x, y)
                _light_cache[key] = v
            return v

        # Per-render memoization for can_see_square (called per tile per POV entity).
        _can_see_square_cache: dict = {}

        def cached_can_see_square(entity, pos, force_dark_vision=False, inclusive=None):
            key = (id(entity), pos, force_dark_vision, inclusive)
            v = _can_see_square_cache.get(key)
            if v is None:
                v = self.map.can_see_square(entity, pos, force_dark_vision=force_dark_vision, inclusive=inclusive)
                _can_see_square_cache[key] = v
            return v

        # Per-render memoization for can_see(entity, target) (called per object/entity).
        _can_see_entity_cache: dict = {}

        def cached_can_see(entity, target, allow_dark_vision=True, active_perception=0):
            key = (id(entity), id(target), allow_dark_vision, active_perception)
            v = _can_see_entity_cache.get(key)
            if v is None:
                v = self.map.can_see(entity, target, allow_dark_vision=allow_dark_vision, active_perception=active_perception)
                _can_see_entity_cache[key] = v
            return v

        if entity_pov is not None and len(entity_pov) > 0:
            entity_pov_locations = []
            if not isinstance(entity_pov, list):
                entity_pov = [entity_pov]
            for entity in entity_pov:
                if entity:
                    for pos in self.map.entity_squares(entity):
                        entity_pov_locations.append(pos)

        self.logger.info(f"entity_pov_locations: {entity_pov_locations}")
        if self.padding:
            width += self.padding[0]
            height += self.padding[1]
            x_offset = self.padding[0] // 2
            y_offset = self.padding[1] // 2
        else:
            x_offset = 0
            y_offset = 0

        for index_1 in range(width):
            x = index_1 - x_offset
            result_row = []
            for index_2 in range(height):
                has_darkvision = False
                hidden_door_tile = False
                hidden_door_line_of_sight = False

                y = height - index_2 - 1 - y_offset
                soft_shadow_direction = [0,0,0,0,0,0,0,0]

                if entity_pov is not None:
                    if not isinstance(entity_pov, list):
                        entity_pov = [entity_pov]

                    entity_pov = [e for e in entity_pov if e]
                    # Optimized distance: avoid numpy array allocation per tile
                    if entity_pov_locations:
                        distance_to_square = min(
                            ((x - pos[0]) ** 2 + (y - pos[1]) ** 2) ** 0.5
                            for pos in entity_pov_locations
                        )
                    else:
                        distance_to_square = None

                    if distance_to_square is not None and any([e.darkvision(distance_to_square * self.map.feet_per_grid) for e in entity_pov if e]):
                        has_darkvision = True
                    else:
                        has_darkvision = False

                    if len(entity_pov) > 0:
                        if not any([cached_can_see_square(entity, (x, y)) for entity in entity_pov]):
                            if any([cached_can_see_square(entity, (x, y), force_dark_vision=True) for entity in entity_pov]):
                                result_row.append({'x': x, 'y': y, 'difficult': self.map.difficult_terrain(entity, x, y), 'line_of_sight': True, 'light': 0.0, 'opacity': 0.95, 'soft_shadow_direction': soft_shadow_direction})
                                continue
                            # check if there is a door like object in the square
                            if self.map.kind_of_door(x, y):
                                hidden_door_tile = True
                                hidden_door_line_of_sight = any([cached_can_see_square(entity, (x, y), force_dark_vision=True, inclusive=False) for entity in entity_pov])
                            else:
                                result_row.append({'x': x, 'y': y, 'difficult': False, 'line_of_sight': False, 'light': 0.0, 'opacity': 1.0, 'soft_shadow_direction': soft_shadow_direction})
                                continue

                # Guard against out-of-bounds coordinates (e.g., padding extending beyond map)
                if x < 0 or y < 0 or x >= self.map.size[0] or y >= self.map.size[1]:
                    result_row.append({'x': x, 'y': y, 'difficult': False, 'line_of_sight': False, 'light': 0.0, 'opacity': 0.0, 'soft_shadow_direction': soft_shadow_direction})
                    continue

                object_entities = self.map.objects_at(x, y)
                entity = self.map.entity_at(x, y)
                light = 0.0 if hidden_door_tile else light_at(x, y)

                darkvision_color = False
                if has_darkvision and not hidden_door_tile:
                    if light == 0.0:
                        darkvision_color = True
                    light += 0.5

                opacity = 0.9 if hidden_door_tile else 1.0 - max(min(1.0, light), 0.2)


                soft_shadow_index = 0
                for offset_x in [-1, 0, 1]:
                    for offset_y in [-1, 0, 1]:
                        if offset_x == 0 and offset_y == 0:
                            continue
                        if x + offset_x < 0 or y + offset_y < 0 or x + offset_x >= self.map.size[0] or y + offset_y >= self.map.size[1]:
                            soft_shadow_direction[soft_shadow_index] = 0
                        elif light_at(x + offset_x, y + offset_y) > light:
                            soft_shadow_direction[soft_shadow_index] = 1
                        else:
                            soft_shadow_direction[soft_shadow_index] = 0
                        soft_shadow_index += 1

                shared_attributes = {
                    'x': x,
                    'y': y,
                    'difficult': False if hidden_door_tile else self.map.difficult_terrain(entity, x, y),
                    'blocked': self.map.base_map[x][y] == '#',
                    'door': bool(self.map.kind_of_door(x, y)),
                    'line_of_sight': hidden_door_line_of_sight if hidden_door_tile else True,
                    'light': light,
                    'soft_shadow_direction': soft_shadow_direction,
                    'opacity': opacity,
                    'has_darkvision': has_darkvision,
                    'darkvision_color': darkvision_color,
                    'is_flying': entity.is_flying() if entity else False,
                    'conversation_languages': []
                }

                def render_objects(entity_pov=None, shared_attrs=None, objects=None, current_entity=None):
                    shared_attrs['objects'] = []
                    for object_entity in objects:
                        viewer_revealed_secret = False
                        if entity_pov and entity_pov != current_entity:
                            viewer_revealed_secret = any([
                                getattr(object_entity, 'perception_results', {}).get(entity_p, {}).get('revealed')
                                for entity_p in entity_pov
                            ])
                            visible_to_pov = any([cached_can_see(entity_p, object_entity, allow_dark_vision=True,
                                                                   active_perception=self.battle.active_perception_for(entity_p) if self.battle and entity_p in self.battle.entities else 0)
                                                  for entity_p in entity_pov])
                            visible_to_pov = visible_to_pov or viewer_revealed_secret
                            if (isinstance(object_entity, DoorObject) or isinstance(object_entity, DoorObjectWall)) \
                                    and not object_entity.concealed() and not object_entity.secret():
                                visible_to_pov = True
                            elif not visible_to_pov:
                                continue
                        object_info = {
                            "id" : object_entity.entity_uid,
                            "name" : object_entity.name,
                            "label" : object_entity.label(),
                            "image" : object_entity.token_image(),
                            "transforms" : object_entity.token_image_transform()
                        }

                        marker_edges = None
                        door_edges = getattr(object_entity, 'door_pos', None)
                        if isinstance(door_edges, list) and len(door_edges) == 4:
                            marker_edges = {
                                'top': bool(door_edges[0]),
                                'right': bool(door_edges[1]),
                                'bottom': bool(door_edges[2]),
                                'left': bool(door_edges[3]),
                            }
                        elif isinstance(door_edges, int):
                            marker_edges = {
                                'top': door_edges == 0,
                                'right': door_edges == 1,
                                'bottom': door_edges == 2,
                                'left': door_edges == 3,
                            }

                        originally_secret_door = bool(
                            object_entity.secret()
                            or viewer_revealed_secret
                            or object_entity.properties.get('secret')
                            or object_entity.secret_perception_dc() is not None
                            or object_entity.properties.get('secret_dc') is not None
                            or (
                                object_entity.properties.get('secret_door')
                                and (
                                    object_entity.secret()
                                    or viewer_revealed_secret
                                    or (hasattr(object_entity, 'opened') and object_entity.opened())
                                )
                            )
                        )
                        is_secret_door = (
                            isinstance(object_entity, DoorObjectWall)
                            and originally_secret_door
                        )
                        object_info['secret_door_marker'] = bool(
                            is_secret_door
                            and not object_info['image']
                            and marker_edges
                            and any(marker_edges.values())
                        )
                        object_info['secret_door_marker_opened'] = bool(
                            object_info['secret_door_marker']
                            and hasattr(object_entity, 'opened')
                            and object_entity.opened()
                        )
                        object_info['secret_door_marker_edges'] = marker_edges or {
                            'top': False,
                            'right': False,
                            'bottom': False,
                            'left': False,
                        }

                        # Visible-teleporter marker (configurable per-instance via
                        # YAML ``visible: true`` on a teleporter). Excludes Chasms,
                        # which have their own visual treatment.
                        is_visible_teleporter = (
                            isinstance(object_entity, Teleporter)
                            and not isinstance(object_entity, Chasm)
                            and getattr(object_entity, 'is_visible_marker', lambda: False)()
                        )
                        object_info['teleporter_marker'] = bool(is_visible_teleporter)
                        object_info['teleporter_marker_color'] = (
                            object_entity.marker_color() if is_visible_teleporter else None
                        )

                        is_grease_surface = isinstance(object_entity, GreaseSurface) or bool(
                            object_entity.properties.get('grease_surface')
                        )
                        object_info['grease_marker'] = bool(is_grease_surface)
                        object_info['grease_marker_seed'] = (
                            object_entity.properties.get('grease_seed') if is_grease_surface else None
                        )

                        object_info['notes'], _ = object_entity.list_notes(entity_pov=entity_pov)
                        if object_entity.properties.get('image_offset_px'):
                            object_info['image_offset_px'] = object_entity.properties.get('image_offset_px')
                        else:
                            object_info['image_offset_px'] = [0, 0]

                        if object_entity.properties.get('token_offset_px'):
                            object_info['token_offset_px'] = object_entity.properties.get('token_offset_px')
                        else:
                            object_info['token_offset_px'] = [0, 0]

                        shared_attrs['objects'].append(object_info)

                        if object_entity.__class__.__name__ == 'Ground':
                            shared_attrs['ground_items'] = object_entity.inventory.keys()

                if entity:
                    if entity_pov and len(entity_pov) > 0:
                        visible_to_pov = any([cached_can_see(entity_p, entity, allow_dark_vision=True) for entity_p in entity_pov])
                        if not visible_to_pov or hidden_door_tile:
                            result_row.append(shared_attributes)
                            continue

                    shared_attributes['in_battle'] = self.battle and entity in self.battle.combat_order
                    m_x, m_y = self.map.entities[entity]
                    render_objects(entity_pov=entity_pov, shared_attrs=shared_attributes, objects=object_entities, current_entity=entity)
                    attributes = shared_attributes.copy()
                    listener_languages = []

                    if entity_pov:
                        for _entity in entity_pov:
                            for language in _entity.languages():
                                if language not in listener_languages:
                                    listener_languages.append(language)

                    attributes.update({
                    'id': entity.entity_uid,
                    'hp': entity.hp(),
                    'max_hp': entity.max_hp(),
                    'entity_size': entity.size(),
                    'dialog': entity.dialog,
                    'conversation_buffer': entity.conversation(listener_languages=listener_languages),
                    'conversation_languages': ",".join(entity.languages() if entity.languages() and hasattr(entity.languages(), '__iter__') and not isinstance(entity.languages(), str) else ['common'])
                    })
                    assert entity.languages() is not None
                    if m_x == x and m_y == y:
                        team_group, team_border_tint = self._team_visuals_for(entity)
                        attributes.update({
                            'entity': entity.token_image(),
                            'name': entity.label(),
                            'label': entity.label(),
                            'hiding' : entity.hidden(),
                            'prone': entity.prone(),
                            'dead': entity.dead(),
                            'unconscious': entity.unconscious(),
                            'effects' : [str(effect['effect']) for effect in entity.current_effects()],
                            'team_group': team_group,
                            'team_border_tint': team_border_tint
                        })
                    result_row.append(attributes)

                else:
                    render_objects(entity_pov=entity_pov, shared_attrs=shared_attributes, objects=object_entities, current_entity=entity)
                    result_row.append(shared_attributes)
            result.append(result_row)
        return result