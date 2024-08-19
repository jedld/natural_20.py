from natural20.item_library.object import Object
from natural20.event_manager import EventManager
from natural20.die_roll import DieRoll

# Represents a staple of DnD the concealed pit trap
class PitTrap(Object):
    def __init__(self, map, properties):
        super().__init__(map, properties=properties)
        self.activated = False

    def area_trigger_handler(self, entity, entity_pos, is_flying):
        result = []
        if entity_pos != self.position:
            return None
        if is_flying:
            return None

        if not self.activated:
            damage = DieRoll.roll(self.properties['damage_die'])
            result = [
                {
                    'source': self,
                    'type': 'state',
                    'params': {
                        'activated': True
                    }
                },
                {
                    'source': self,
                    'target': entity,
                    'type': 'damage',
                    'attack_name': self.properties.get('attack_name', 'pit trap'),
                    'damage_type': self.properties.get('damage_type', 'piercing'),
                    'damage': damage
                }
            ]

        return result

    def placeable(self):
        return not self.activated

    def label(self):
        if not self.activated:
            return 'ground'

        return self.properties.get('name', 'pit trap')

    def passable(self):
        return True

    def token(self):
        return ["\u02ac"]

    def concealed(self):
        return not self.activated

    def jump_required(self):
        return self.activated

    def setup_other_attributes(self):
        self.activated = False
