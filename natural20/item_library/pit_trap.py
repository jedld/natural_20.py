from natural20.item_library.object import Object
from natural20.event_manager import EventManager
from natural20.die_roll import DieRoll
from natural20.concern.generic_event_handler import GenericEventHandler
import pdb

# Represents a staple of DnD the concealed pit trap
class PitTrap(Object):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties=properties)
        self.activated = False
        self.damages = properties.get('damages', [])
        self.events = properties.get('events', [])

    def to_dict(self):
        hash = super().to_dict()
        hash['activated'] = self.activated
        return hash

    @staticmethod
    def from_dict(hash):
        session = hash['session']
        pit_trap = PitTrap(session, None, hash['properties'])
        pit_trap.activated = hash['activated']
        return pit_trap

    def token_image(self):
        if self.properties.get('token_image'):
            if self.activated:
                return self.properties.get('token_image')

        return None

    def area_trigger_handler(self, entity, entity_pos, is_flying):
        result = []
        if entity_pos !=  self.map.position_of(self):
            return None
        if is_flying:
            return None
        result = []
        if not self.activated:
            if self.damages:
                for damage in self.damages:
                    result.append({
                        'source': self,
                        'target': entity,
                        'type': 'damage',
                        'attack_name': damage.get('attack_name', 'pit trap'),
                        'damage_type': damage.get('damage_type', 'piercing'),
                        'damage': DieRoll.roll(damage['damage_die'])
                    })
            else:
                result.append({
                    'source': self,
                    'target': entity,
                    'type': 'damage',
                    'attack_name': self.properties.get('attack_name', 'pit trap'),
                    'damage_type': self.properties.get('damage_type', 'piercing'),
                    'damage': DieRoll.roll(self.properties['damage_die'])
                })
            result.append({
                'source': self,
                'target': entity,
                'type': 'state',
                'params': {
                    'activated': True
                },
                'trigger': 'activate'
            })
            result.append({
                'source': self,
                'target': entity,
                'type': 'cancel_move'
            })

        return result

    def placeable(self):
        return not self.activated

    def label(self):
        if not self.activated:
            return 'ground'

        return self.properties.get('name', 'pit trap')

    def passable(self, origin=None):
        return True

    def token(self):
        return ["\u02ac"]

    def concealed(self):
        return not self.activated

    def jump_required(self):
        return self.activated

    def setup_other_attributes(self):
        self.activated = False
