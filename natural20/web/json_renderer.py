import numpy as np
class JsonRenderer:
    def __init__(self, map, battle=None):
        self.map = map
        self.battle = battle

    def render(self, entity_pov=None, path=None, select_pos=None):
        if path is None:
           path = []
        result = []
        width, height = self.map.size
        for index_1 in range(width):
            x = index_1
            result_row = []
            for index_2 in range(height):
                y = height - index_2 - 1
                if entity_pov is not None:
                    if not isinstance(entity_pov, list):
                        entity_pov = [entity_pov]
                    if len(entity_pov) > 0:
                        if not any([self.map.can_see_square(entity, (x, y)) for entity in entity_pov]):
                            result_row.append({'x': x, 'y': y, 'difficult': False, 'line_of_sight': False, 'light': 0.0, 'opacity': 0.0})
                            continue

                entity = self.map.entity_at(x, y)
                light = self.map.light_at(x, y)
                opacity = 1.0 - max(min(1.0, light), 0.3)

                shared_attributes = {
                    'x': x,
                    'y': y,
                    'difficult': self.map.difficult_terrain(entity, x, y),
                    'line_of_sight': True,
                    'light': light,
                    'opacity': opacity,
                }

                if entity:
                    shared_attributes['in_battle'] = self.battle and entity in self.battle.combat_order
                    m_x, m_y = self.map.entities[entity]
                    attributes = shared_attributes.copy()
                    attributes.update({
                    'id': entity.entity_uid, 'hp': entity.hp(), 'max_hp': entity.max_hp(), 'entity_size': entity.size()
                    })
                    if m_x == x and m_y == y:
                        attributes.update({
                            'entity': entity.token_image(), 'name': entity.label(), 'dead': entity.dead(), 'unconscious': entity.unconscious()
                        })
                    result_row.append(attributes)
                else:
                    result_row.append(shared_attributes)
            result.append(result_row)
        return result