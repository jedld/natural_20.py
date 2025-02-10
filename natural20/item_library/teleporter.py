from natural20.item_library.object import Object
from typing import Optional
from natural20.entity import Entity
import pdb

class Teleporter(Object):
    def __init__(self, map, properties):
        super().__init__(map, properties)
        self.target_map = properties.get('target_map', None)

        self.target_position = properties['target_position']

    def on_enter(self, entity: Entity, map, battle=None):
        if self.target_map:
            map.linked_maps[self.target_map].place(self.target_position, entity)
            map.remove(entity)
        else:
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

    def setup_other_attributes(self):
        pass