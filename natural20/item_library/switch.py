from natural20.item_library.object import Object
from natural20.event_manager import EventManager
from natural20.concern.generic_event_handler import GenericEventHandler
import pdb
class Switch(Object):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties)
        self.switch_id = self.properties.get('id')
        self.state = self.properties.get('state', 'off')
        self.on_event = self.properties.get('on_event')
        self.off_event = self.properties.get('off_event')
        self.on_message = self.properties.get('on_message')
        self.off_message = self.properties.get('off_message')

    def interactable(self, entity=None):
        return not self.is_concealed

    def available_interactions(self, entity, battle=None, admin=False):
        interactions = super().available_interactions(entity, battle, admin=admin)
        if self.interact_distance == 0:
            ex, ey = self.map.position_of(entity)
            dx, dy = self.map.position_of(self)
            if not ex == dx or not ey == dy:
                return interactions

        if not self.is_concealed or admin:
            if self.state == 'off':
                interactions['on'] = {}
            else:
                interactions['off'] = {}

        return interactions

    def resolve(self, entity, action, other_params, opts=None):
        result = {}
        if opts is None:
            opts = {}
        if action == 'on':
            self.state = 'on'
            return {
                'action': 'on',
                'source': entity,
                'target': self
            }
        elif action == 'off':
            self.state = 'off'
            return {
                'action': 'off',
                'source': entity,
                'target': self
            }
        return result

    def use(self, entity, result, session=None):
        action = result.get('action')
        if action == 'on':
            self.state = 'on'
            self.resolve_trigger('on')
        elif action == 'off':
            self.state = 'off'
            self.resolve_trigger('off')
        return self