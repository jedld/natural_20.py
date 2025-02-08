from natural20.item_library.object import Object
from natural20.concern.container import Container
from natural20.item_library.chest import Chest
from natural20.concern.lootable import Lootable
from natural20.concern.inventory import Inventory
import pdb

class Fireplace(Object, Lootable, Inventory, Container):
    def __init__(self, map, properties=None):
        super().__init__(map, properties)
        self.lit = properties.get('lit', False)
        self.bright = properties.get('light', {}).get('bright', 20)
        self.dim = properties.get('light', {}).get('dim', 10)
        self.load_inventory()

    def build_map(self, action, action_object):
        if action == 'light':
            return action_object
        elif action == 'put_out':
            return action_object
        elif action == 'loot':
            def next_action(items):
                action_object.other_params = items
                return action_object
             
            return {
                'action': action_object,
                'param': [{
                    'type': 'select_items',
                    'label': self.items_label(),
                    'items': self.inventory
                }],
                'next': next_action
            }

    def is_lit(self):
        return self.lit

    def opaque(self, origin=None):
        return False

    def passable(self, origin=None):
        return True

    def available_interactions(self, entity, battle=None):
        interactions = {}
        if self.is_lit():
            interactions['put_out'] = {}
        elif entity.has_item('torch'):
            interactions['light'] = {}
        interactions['loot'] = {}
        return interactions

    def is_interactable(self):
        return True

    def resolve(self, entity, action, other_params, opts=None):
        if opts is None:
            opts = {}

        if action == 'light':
            return {'action': action }
        elif action == 'put_out':
            return {'action': action}
        else:
            return super().resolve(entity, action, other_params, opts)
        return None

    def use(self, entity, result, session=None):
        action = result.get('action')
        if action == 'light':
            self.lit = True
        elif action == 'put_out':
            self.lit = False
        Lootable.use(self, entity, result, session)

    def light_properties(self):
        if self.lit:
            dim = self.bright
            bright = self.dim
        else:
            dim = 0
            bright = 0

        return {'dim': dim, 'bright': bright}

    def interactable(self):
        return True