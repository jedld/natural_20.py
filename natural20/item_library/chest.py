from natural20.item_library.object import Object
from natural20.concern.container import Container
import pdb

class Chest(Object, Container):
    def __init__(self, map, properties=None):
        super().__init__(map, properties)
        self.front_direction = self.properties.get('front_direction', 'auto')
        self.properties = properties or {}
        self.state = (self.properties.get('state') or 'closed')
        self.is_locked = self.properties.get('locked', False)
        self.key_name = self.properties.get('key', '')

        inventory = self.properties.get('inventory', [])
        self.inventory = {}
        for item in inventory:
            self.add_item(item['type'], item['qty'])

    def facing(self):
        # face away from a wall if possible
        if self.front_direction == 'auto':
            pos = self.map.position_of(self)
            if self.map.wall(pos[0] - 1, pos[1]):
                self.front_direction = 'up'
            elif self.map.wall(pos[0] + 1, pos[1]):
                self.front_direction = 'down'
            elif self.map.wall(pos[0], pos[1] - 1):
                self.front_direction = 'left'
            elif self.map.wall(pos[0], pos[1] + 1):
                self.front_direction = 'right'
            else:
                self.front_direction = 'up'

    def build_map(self, action, action_object):
        if action == 'store':
            return {
                'action': action_object,
                'param': [{
                    'type': 'select_items',
                    'label': action_object.source.items_label(),
                    'items': action_object.source.inventory
                }],
                'next': lambda items: {
                    'param': None,
                    'next': lambda: action_object
                }
            }
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
        return action_object

    def opaque(self, origin=None):
        return False

    def unlock(self):
        self.is_locked = False

    def lock(self):
        self.is_locked = True

    def locked(self):
        return self.is_locked

    def passable(self, origin=None):
        return True

    def closed(self):
        return self.state == 'closed'

    def opened(self):
        return self.state == 'opened'

    def open(self):
        self.state = 'opened'

    def close(self):
        self.state = 'closed'

    def token_image(self):
        if self.properties.get('token_image'):
            if self.opened():
                return self.properties.get('token_image') + '_opened'
            else:
                return self.properties.get('token_image') + '_closed'

        return None
    
    def token_image_transform(self):
        # apply css style to rotate the image relative to the right hinge
        # depending on the direction of the door
        # Set transform-origin based on facing direction
        transform = " transform: translate(50%, 50%)"

        # Now apply rotation and translation

        if self.facing() == "up":
            transform += " rotate(0deg);"
        elif self.facing() == "down":
            transform += " rotate(180deg);"
        elif self.facing() == "left":
            transform += " rotate(-90deg)"
        elif self.facing() == "right":
            transform += " rotate(90deg);"
        return transform

    def token(self):
        # dead? was not defined in snippet; adapt or remove as needed
        return ["\u2610"]  # Example placeholder

    def color(self):
        return 'white' if self.is_opened() else 'default'

    def available_interactions(self, entity, battle=None):
        if self.locked():
            interactions = {
                'unlock': {
                    'disabled': not (entity.item_count(self.key_name) > 0),
                    'disabled_text': 'Key required'
                }
            }
            # Example lockpick check
            if entity.item_count('thieves_tools') > 0 and entity.proficient('thieves_tools'):
                interactions['lockpick'] = {
                    'disabled': not entity.action_available(battle),
                    'disabled_text': 'Action needed'
                }
            return interactions
        else:
            if self.opened():
                return {
                    'close': {},
                    'store': {},
                    'loot': {}
                }
            else:
                return {
                    'open': {},
                    'lock': {
                        'disabled': not (entity and entity.item_count(self.key_name) > 0),
                        'disabled_text': 'Key required'
                    }
                }

    def is_interactable(self):
        return True

    def resolve(self, entity, action, other_params, opts=None):
        if opts is None:
            opts = {}

        if action == 'open':
            return {'action': action } if not self.locked() else {'action': 'door_locked'}
        elif action in ['loot', 'store']:
            return {
                'action': action,
                'items': other_params,
                'source': entity,
                'target': self,
                'battle': opts.get('battle')
            }
        elif action == 'close':
            return {'action': action}
        elif action == 'lockpick':
            roll = entity.lockpick(opts.get('battle'))
            if roll.result >= self.lockpick_dc():
                return {'action': 'lockpick_success', 'roll': roll, 'cost': 'action'}
            else:
                return {'action': 'lockpick_fail', 'roll': roll, 'cost': 'action'}
        elif action == 'unlock':
            return {'action': 'unlock'} if entity.item_count(self.key_name) > 0 else {'action': 'unlock_failed'}
        elif action == 'lock':
            return {'action': 'lock'} if entity.item_count(self.key_name) > 0 else {'action': 'lock_failed'}
        return None

    def use(self, entity, result):
        action = result.get('action')
        if action == 'store':
            self.store(result.get('battle'), result.get('source'), result.get('target'), result.get('items'))
        elif action == 'loot':
            self.transfer(result.get('battle'), result.get('source'), result.get('target'), result.get('items'))
        elif action == 'open':
            if self.closed():
                self.open()
        elif action == 'close':
            if self.opened():
                self.close()
        elif action == 'lockpick_success':
            if self.is_locked():
                self.unlock()
        elif action == 'lockpick_fail':
            if self.is_locked():
                entity.deduct_item('thieves_tools')
        elif action == 'unlock':
            if self.is_locked():
                self.unlock()
        elif action == 'lock':
            if not self.is_locked():
                self.lock()

    def lockpick_dc(self):
        return self.properties.get('lockpick_dc', 10)

    def interactable(self):
        return True