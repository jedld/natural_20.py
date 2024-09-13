class JsonRenderer:
    def __init__(self, map, battle=None):
        self.map = map
        self.battle = battle

    def render(self, line_of_sight=None, path=None, select_pos=None):
        if path is None:
           path = []
        result = []
        width, height = self.map.size
        for index_1 in range(width):
            x = index_1
            result_row = []
            for index_2 in range(height):
                y = height - index_2 - 1
                entity = self.map.entity_at(x, y)
                shared_attributes = {
                    'x': x, 'y': y, 'difficult': self.map.difficult_terrain(entity, x, y)
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