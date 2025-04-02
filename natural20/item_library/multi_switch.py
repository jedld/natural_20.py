from natural20.item_library.object import Object
from natural20.event_manager import EventManager
from natural20.concern.generic_event_handler import GenericEventHandler
import pdb
class MultiSwitch(Object):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties)
        self.switch_id = self.properties.get('id')
        self.states = self.properties.get('states', ['on', 'off'])
        self.state = self.properties.get('state', 'off')
        self.enabled = self.properties.get('enabled', True)

    def interactable(self, entity=None):
        return not self.is_concealed

    def available_interactions(self, entity, battle=None, admin=False):
        interactions = super().available_interactions(entity, battle, admin=admin)
        if self.interact_distance == 0:
            ex, ey = self.map.position_of(entity)
            dx, dy = self.map.position_of(self)
            if not ex == dx or not ey == dy:
                return interactions

        if self.enabled and (not self.is_concealed or admin):
            if self.properties.get('if'):
                conditions = self.properties['if']
                if not self.eval_if(conditions, context={'target': entity}):
                    return interactions

            for state in self.states:
                if state != self.state:
                    interactions[state] = {}

        return interactions

    def resolve(self, entity, action, other_params, opts=None):
        result = {}
        if opts is None:
            opts = {}
        if action in self.states:
            self.state = action
            return {
                'action': action,
                'source': entity,
                'target': self
            }
        return result

    def use(self, entity, result, session=None):
        action = result.get('action')
        if action in self.states:
            if action != self.state:
                self.state = action
                self.resolve_trigger(action)
        return self