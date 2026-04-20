from natural20.item_library.object import Object
from natural20.concern.container import Container
from natural20.item_library.chest import Chest
from natural20.concern.lootable import Lootable
from natural20.concern.inventory import Inventory
import pdb

class Fireplace(Object):
    def __init__(self, session, map, properties=None):
        super().__init__(session, map, properties)
        self.session = session
        self.lit = properties.get('lit', False)
        self.bright = properties.get('light', {}).get('bright', 20)
        self.dim = properties.get('light', {}).get('dim', 10)


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

    def available_interactions(self, entity, battle=None, admin=False):
        if self.dead():
            return {}
        interactions = {}
        if self.is_lit():
            interactions['put_out'] = {}
        elif entity.has_item('torch') or admin:
            interactions['light'] = {}
        interactions['loot'] = {}
        return interactions

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
        _result = super().use(entity, result, session)
        if not _result:
            action = result.get('action')
            if action == 'light':
                self.lit = True
                if self.session:
                    self.session.event_manager.received_event({
                        'source': entity,
                        'target': self,
                        'event': 'object_interaction',
                        'sub_type': 'light',
                        'result': 'success',
                        'reason': f'{entity.name} lights the fireplace.'
                    })
            elif action == 'put_out':
                self.lit = False
                if self.session:
                    self.session.event_manager.received_event({
                        'source': entity,
                        'target': self,
                        'event': 'object_interaction',
                        'sub_type': 'put_out',
                        'result': 'success',
                        'reason': f'{entity.name} extinguishes the fireplace.'
                    })
        return _result

    def take_damage(self, dmg, battle=None, damage_type='piercing', **kwargs):
        if damage_type == 'fire' and not self.lit and not self.dead():
            self.lit = True
            if self.session:
                self.session.event_manager.received_event({
                    'source': self,
                    'target': self,
                    'event': 'object_interaction',
                    'sub_type': 'ignite',
                    'result': 'success',
                    'reason': 'The fireplace roars to life as the flames ignite it.'
                })
        super().take_damage(dmg, battle=battle, damage_type=damage_type, **kwargs)
        if self.dead() and self.lit:
            self.lit = False

    def light_properties(self):
        if self.lit and not self.dead():
            dim = self.bright
            bright = self.dim
        else:
            dim = 0
            bright = 0

        return {'dim': dim, 'bright': bright}

    def interactable(self, entity=None):
        return not self.dead()
    
    def from_dict(hash):
        session = hash['session']
        fireplace = Fireplace(session, None, hash['properties'])
        fireplace.lit = hash['lit']
        fireplace.entity_uid = hash['entity_uid']
        fireplace.inventory = hash['inventory']
        return fireplace

    def to_dict(self):
        hash = super().to_dict()
        hash['lit'] = self.lit
        hash['inventory'] = self.inventory
        return hash