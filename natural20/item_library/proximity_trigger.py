from natural20.item_library.object import Object
from natural20.event_manager import EventManager
from natural20.die_roll import DieRoll
from natural20.concern.generic_event_handler import GenericEventHandler
import pdb

class ProximityTrigger(Object):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties=properties)
        self.distance = self.properties.get('distance', 1)
        self.activated = False
        self.events = self.properties.get('events', [])

        for event in self.events:
            handler = GenericEventHandler(session, map, event)
            self.register_event_hook(event['event'], handler, 'handle')

    def area_trigger_handler(self, entity, entity_pos, is_flying):
        result = []

        object_position = self.map.position_of(self)

        if not self.activated:
            if self.within_distance(object_position, entity_pos):
                result.append({
                    'source': self,
                    'type': 'state',
                    'params': {
                        'activated': True
                    },
                    'trigger': 'activate'
                })
        return result

    def interactable(self):
        return False

    def available_interactions(self, entity, battle=None, admin=False):
        return {}

    def setup_other_attributes(self):
        self.activated = False

    def within_distance(self, object_position, entity_pos):
        return abs(object_position[0] - entity_pos[0]) <= self.distance and abs(object_position[1] - entity_pos[1]) <= self.distance
