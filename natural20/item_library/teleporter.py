from natural20.item_library.object import Object
from typing import Optional
from natural20.entity import Entity
import pdb

class Teleporter(Object):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties)
        self.target_map = properties.get('target_map', None)

        self.target_position = properties['target_position']

    def on_enter(self, entity: Entity, map, battle=None):
        if self.target_map:
            target_map = map.linked_maps[self.target_map]
            entity_placed = False
            if target_map.placeable(entity, *self.target_position):
                target_map.place(self.target_position, entity)
                entity_placed = True
            else:
                # look for adjacent positions
                for dx in range(-1, 2):
                    if entity_placed:
                        break
                    for dy in range(-1, 2):
                        if target_map.placeable(entity, self.target_position[0] + dx, self.target_position[1] + dy):
                            target_map.place((self.target_position[0] + dx, self.target_position[1] + dy), entity)
                            map.linked_maps[self.target_map]
                            entity_placed = True
                            break
            if entity_placed:
                map.remove(entity)
        else:
            if map.placeable(entity, *self.target_position, battle):
                map.move_to(entity, *self.target_position, battle)

    def placeable(self):
        return True

    def label(self):
        return 'ground'

    def passable(self, origin=None):
        return True

    def concealed(self):
        return False

    def jump_required(self):
        return False
    
    def to_dict(self):
        hash =  super().to_dict()
        hash['target_map'] = self.target_map
        hash['target_position'] = self.target_position
        return hash
    
    @staticmethod
    def from_dict(hash):
        session = hash['session']
        teleporter = Teleporter(session, None, hash['properties'])
        teleporter.entity_uid = hash['entity_uid']
        teleporter.target_map = hash['target_map']
        teleporter.target_position = hash['target_position']
        return teleporter