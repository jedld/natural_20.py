import numpy as np
import pdb
from natural20.map import Map
from natural20.battle import Battle
class JsonRenderer:
    def __init__(self, map: Map, battle: Battle=None, padding=None):
        self.map = map
        self.battle = battle
        self.padding = padding

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
                if entity_pov is not None:
                    if not isinstance(entity_pov, list):
                        entity_pov = [entity_pov]

                    entity_pov = [e for e in entity_pov if e]
                    distance_to_square = min([np.linalg.norm(np.array((x, y)) - np.array((pos[0], pos[1]))) for pos in entity_pov_locations]) if entity_pov_locations else None

                    if any([e.darkvision(distance_to_square * self.map.feet_per_grid) for e in entity_pov if e]):
                        has_darkvision = True
                    else:
                        has_darkvision = False

                    if len(entity_pov) > 0:
                        if x < 0 or y < 0 or x >= self.map.size[0] or y >= self.map.size[1]:
                            result_row.append({'x': x, 'y': y, 'difficult': False, 'line_of_sight': False, 'light': 0.0, 'opacity': 0.0})
                            continue

                        if not any([self.map.can_see_square(entity, (x, y)) for entity in entity_pov]):
                            if any([self.map.can_see_square(entity, (x, y), force_dark_vision=True) for entity in entity_pov]):
                                result_row.append({'x': x, 'y': y, 'difficult': False, 'line_of_sight': True, 'light': 0.0, 'opacity': 0.95})
                                continue

                            result_row.append({'x': x, 'y': y, 'difficult': False, 'line_of_sight': False, 'light': 0.0, 'opacity': 1.0})
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

                shared_attributes = {
                    'x': x,
                    'y': y,
                    'difficult': self.map.difficult_terrain(entity, x, y),
                    'line_of_sight': True,
                    'light': light,
                    'opacity': opacity,
                    'has_darkvision': has_darkvision,
                    'darkvision_color': darkvision_color
                }

                def render_objects(entity_pov=None):
                    shared_attributes['objects'] = []
                    for object_entity in object_entities:
                        if entity_pov and entity_pov != entity:
                            visible_to_pov = any([self.map.can_see(entity_p, object_entity, allow_dark_vision=True) for entity_p in entity_pov])
                            if not visible_to_pov:
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

                        shared_attributes['objects'].append(object_info)

                        if object_entity.__class__.__name__ == 'Ground':
                            shared_attributes['ground_items'] = object_entity.inventory.keys()

                if entity:
                    if entity_pov and len(entity_pov) > 0:
                        visible_to_pov = any([self.map.can_see(entity_p, entity, allow_dark_vision=True) for entity_p in entity_pov])
                        if not visible_to_pov:
                            result_row.append(shared_attributes)
                            continue

                    shared_attributes['in_battle'] = self.battle and entity in self.battle.combat_order
                    m_x, m_y = self.map.entities[entity]
                    render_objects(entity_pov=entity_pov)
                    attributes = shared_attributes.copy()
                    attributes.update({
                    'id': entity.entity_uid, 'hp': entity.hp(), 'max_hp': entity.max_hp(), 'entity_size': entity.size()
                    })
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
                    render_objects(entity_pov=entity_pov)
                    result_row.append(shared_attributes)
            result.append(result_row)
        return result