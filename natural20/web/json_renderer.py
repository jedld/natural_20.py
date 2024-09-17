import numpy as np
import pdb
class JsonRenderer:
    def __init__(self, map, battle=None):
        self.map = map
        self.battle = battle

    def render(self, entity_pov=None, path=None, select_pos=None):
        if path is None:
           path = []
        result = []
        entity_pov_locations = None
        width, height = self.map.size

        if entity_pov is not None:
            entity_pov_locations = []
            if not isinstance(entity_pov, list):
                entity_pov = [entity_pov]
            for entity in entity_pov:
                for pos in self.map.entity_squares(entity):
                    entity_pov_locations.append(pos)

            

        for index_1 in range(width):
            x = index_1
            result_row = []
            for index_2 in range(height):
                has_darkvision = False

                y = height - index_2 - 1
                if entity_pov is not None:
                    if not isinstance(entity_pov, list):
                        entity_pov = [entity_pov]

                    distance_to_square = min([np.linalg.norm(np.array((x, y)) - np.array((pos[0], pos[1]))) for pos in entity_pov_locations]) if entity_pov_locations else None

                    if any([e.darkvision(distance_to_square * self.map.feet_per_grid) for e in entity_pov]):
                        has_darkvision = True
                    else:
                        has_darkvision = False

                    if len(entity_pov) > 0:
                        if not any([self.map.can_see_square(entity, (x, y)) for entity in entity_pov]):
                            result_row.append({'x': x, 'y': y, 'difficult': False, 'line_of_sight': False, 'light': 0.0, 'opacity': 0.0})
                            continue

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

                if entity:
                    if entity_pov and len(entity_pov) > 0:
                        visible_to_pov = any([self.map.can_see(entity_p, entity, allow_dark_vision=True) for entity_p in entity_pov])
                        if not visible_to_pov:
                            result_row.append(shared_attributes)
                            continue

                    shared_attributes['in_battle'] = self.battle and entity in self.battle.combat_order
                    m_x, m_y = self.map.entities[entity]
                    attributes = shared_attributes.copy()
                    attributes.update({
                    'id': entity.entity_uid, 'hp': entity.hp(), 'max_hp': entity.max_hp(), 'entity_size': entity.size()
                    })
                    if m_x == x and m_y == y:
                        attributes.update({
                            'entity': entity.token_image(), 'name': entity.label(),
                            'hiding' : entity.hidden(),
                            'dead': entity.dead(), 'unconscious': entity.unconscious()
                        })
                    result_row.append(attributes)
                else:
                    result_row.append(shared_attributes)
            result.append(result_row)
        return result