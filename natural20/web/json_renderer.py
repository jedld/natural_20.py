import numpy as np
import pdb
from natural20.map import Map
from natural20.battle import Battle
from natural20.item_library.door_object import DoorObject, DoorObjectWall
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

    def render(self, entity_pov=None, path=None, select_pos=None):
        if path is None:
           path = []
        result = []
        entity_pov_locations = None
        width, height = self.map.size

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

                y = height - index_2 - 1 - y_offset
                soft_shadow_direction = [0,0,0,0,0,0,0,0]

                if entity_pov is not None:
                    if not isinstance(entity_pov, list):
                        entity_pov = [entity_pov]

                    entity_pov = [e for e in entity_pov if e]
                    distance_to_square = min([np.linalg.norm(np.array((x, y)) - np.array((pos[0], pos[1]))) for pos in entity_pov_locations]) if entity_pov_locations else None

                    if distance_to_square is not None and any([e.darkvision(distance_to_square * self.map.feet_per_grid) for e in entity_pov if e]):
                        has_darkvision = True
                    else:
                        has_darkvision = False

                    if len(entity_pov) > 0:
                        if x < 0 or y < 0 or x >= self.map.size[0] or y >= self.map.size[1]:
                            result_row.append({'x': x, 'y': y, 'difficult': False, 'line_of_sight': False, 'light': 0.0, 'opacity': 0.0, 'soft_shadow_direction': soft_shadow_direction})
                            continue

                        if not any([self.map.can_see_square(entity, (x, y)) for entity in entity_pov]):
                            if any([self.map.can_see_square(entity, (x, y), force_dark_vision=True) for entity in entity_pov]):
                                result_row.append({'x': x, 'y': y, 'difficult': False, 'line_of_sight': True, 'light': 0.0, 'opacity': 0.95, 'soft_shadow_direction': soft_shadow_direction})
                                continue
                            # check if there is a door like object in the square
                            if self.map.kind_of_door(x, y):
                                line_of_sight = any([self.map.can_see_square(entity, (x, y), force_dark_vision=True, inclusive=False) for entity in entity_pov])
                                result_row.append({'x': x, 'y': y, 'difficult': False, 'line_of_sight': line_of_sight, 'light': 0.0, 'opacity': 0.8, 'soft_shadow_direction': soft_shadow_direction})
                            else:
                                result_row.append({'x': x, 'y': y, 'difficult': False, 'line_of_sight': False, 'light': 0.0, 'opacity': 1.0, 'soft_shadow_direction': soft_shadow_direction})
                                continue

                object_entities = self.map.objects_at(x, y)
                entity = self.map.entity_at(x, y)
                light = self.map.light_at(x, y)

                darkvision_color = False
                if has_darkvision:
                    if light == 0.0:
                        darkvision_color = True
                    light += 0.5

                opacity = 1.0 - max(min(1.0, light), 0.2)


                soft_shadow_index = 0
                for offset_x in [-1, 0, 1]:
                    for offset_y in [-1, 0, 1]:
                        if offset_x == 0 and offset_y == 0:
                            continue
                        if x + offset_x < 0 or y + offset_y < 0 or x + offset_x >= self.map.size[0] or y + offset_y >= self.map.size[1]:
                            soft_shadow_direction[soft_shadow_index] = 0
                        elif self.map.light_at(x + offset_x, y + offset_y) > light:
                            soft_shadow_direction[soft_shadow_index] = 1
                        else:
                            soft_shadow_direction[soft_shadow_index] = 0
                        soft_shadow_index += 1

                shared_attributes = {
                    'x': x,
                    'y': y,
                    'difficult': self.map.difficult_terrain(entity, x, y),
                    'line_of_sight': True,
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
                        if entity_pov and entity_pov != current_entity:
                            visible_to_pov = any([self.map.can_see(entity_p, object_entity, allow_dark_vision=True) for entity_p in entity_pov])
                            if isinstance(object_entity, DoorObject) or isinstance(object_entity, DoorObjectWall):
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
                        visible_to_pov = any([self.map.can_see(entity_p, entity, allow_dark_vision=True) for entity_p in entity_pov])
                        if not visible_to_pov:
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
                    'conversation_languages': ",".join(entity.languages())
                    })
                    assert entity.languages() is not None
                    if m_x == x and m_y == y:
                        attributes.update({
                            'entity': entity.token_image(),
                            'name': entity.label(),
                            'label': entity.label(),
                            'hiding' : entity.hidden(),
                            'prone': entity.prone(),
                            'dead': entity.dead(), 'unconscious': entity.unconscious(),
                            'effects' : [str(effect['effect']) for effect in entity.current_effects()]
                        })
                    result_row.append(attributes)

                else:
                    render_objects(entity_pov=entity_pov, shared_attrs=shared_attributes, objects=object_entities, current_entity=entity)
                    result_row.append(shared_attributes)
            result.append(result_row)
        return result