from natural20.item_library.object import Object
from natural20.item_library.teleporter import Teleporter
from natural20.item_library.door_object import DoorObject
from typing import Optional
from natural20.entity import Entity
import pdb

class TrapDoor(DoorObject, Teleporter):
    def __init__(self, session, map, properties):
        DoorObject.__init__(self, session, map, properties)
        Teleporter.__init__(self, session, map, properties)
        self.target_map = properties.get('target_map', None)
        self.target_position = properties['target_position']

    def on_enter(self, entity: Entity, map, battle=None):
        if self.closed():
            return
        Teleporter.on_enter(self, entity, map, battle)

    def passable(self, origin=None):
        return True
    
    def opaque(self, origin=None):
        return False

    def placeable(self):
        return True

    def token_image(self):
        if self.properties.get('token_image'):
            if self.opened():
                return f"objects/{self.properties.get('token_image')}" + '_opened'
            else:
                return f"objects/{self.properties.get('token_image')}" + '_closed'

        return None
    
    def token_image_transform(self):
        return None

    def interactable(self, entity=None):
        if self.concealed():
            return False
        return True
    
    def concealed(self):
        return self.is_concealed
    
    def label(self):
        return self.properties.get('label', 'object.trap_door.label')

    def available_interactions(self, entity, battle=None, admin=False):
        if self.concealed() and not admin:
            return {}

        def inside_range():
            if admin:
                return True
            ex, ey = self.map.position_of(entity)
            dx, dy = self.map.position_of(self)

            for x in range(-1, 2):
                for y in range(-1, 2):
                    if x == 0 and y == 0:
                        continue
                    if ex + x == dx and ey + y == dy:
                        return True

        actions = {}
        if entity:
            has_key = entity.item_count(self.key_name) > 0 or admin
        else:
            has_key = False

        if self.locked:
            actions["unlock"] = {
                "disabled": not has_key,
                "disabled_text": "object.door.key_required"
            }
            if entity.item_count("thieves_tools") > 0 and entity.proficient("thieves_tools"):
                if battle:
                    actions["lockpick"] = {
                        "disabled": entity.action(battle),
                        "disabled_text": "object.door.action_required"
                    }
                else:
                    actions["lockpick"] = {}
            if self.privacy_lock and inside_range():
                actions["unlock"] = {}
            return actions

        if self.opened() and inside_range():
            return {
                "close": {
                    "disabled": self.someone_blocking_the_doorway(),
                    "disabled_text": "object.door.door_blocked"
                }
            }

        if inside_range():
            actions["open"] = {}

        if self.privacy_lock and self.lockable and inside_range():
            actions["lock"] = {}
        elif self.lockable:
            actions["lock"] = {
                "disabled": not has_key,
                "disabled_text": "object.door.key_required"
            }
        return actions
    
    def to_dict(self):
        hash =  super().to_dict()
        hash['target_map'] = self.target_map
        hash['target_position'] = self.target_position
        return hash
    
    @staticmethod
    def from_dict(hash):
        session = hash['session']
        trap_door = TrapDoor(session, None, hash['properties'])
        trap_door.entity_uid = hash['entity_uid']
        trap_door.target_map = hash['target_map']
        trap_door.target_position = hash['target_position']
        return trap_door


