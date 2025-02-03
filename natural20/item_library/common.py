from natural20.item_library.object import Object
from natural20.concern.container import Container

class StoneWall(Object):
    def __init__(self, map, properties):
        super().__init__(map, properties)

    def opaque(self):
        return not self.dead()

    def passable(self):
        return self.dead()

    def token(self):
        if self.dead():
            return ['`']
        else:
            return ['#']


class Ground(Object, Container):
    def __init__(self, map, properties):
        super().__init__(map, properties)
        self.state = None
        self.locked = None
        self.key_name = None

    def build_map(self, action, action_object):
        if action == 'drop':
            return {
                'action': action_object,
                'param': [
                    {
                        'type': 'select_items',
                        'label': action_object.source.items_label,
                        'items': action_object.source.inventory
                    }
                ],
                'next': lambda items: {
                    'param': None,
                    'next': lambda: action_object
                }
            }
        elif action == 'pickup':
            return {
                'action': action_object,
                'param': [
                    {
                        'type': 'select_items',
                        'label': self.items_label,
                        'items': self.inventory
                    }
                ],
                'next': lambda items: {
                    'param': None,
                    'next': lambda: action_object
                }
            }

    def opaque(self):
        return False

    def passable(self):
        return True

    def placeable(self):
        return True

    def token(self):
        return ["\u00B7".encode('utf-8')]

    def color(self):
        return 'cyan'

    def available_interactions(self, entity, battle=None):
        return []

    def interactable(self):
        return False

    def resolve(self, entity, action, other_params, opts={}):
        if action is None:
            return

        if action == 'drop' or action == 'pickup':
            return {
                'action': action,
                'items': other_params,
                'source': entity,
                'target': self,
                'battle': opts.get('battle')
            }

    def use(self, entity, result):
        if result['action'] == 'drop':
            self.store(result['battle'], result['source'], result['target'], result['items'])
        elif result['action'] == 'pickup':
            self.transfer(result['battle'], result['source'], result['target'], result['items'])

    def list_notes(self, entity, perception, highlight=False):
        return [self.t("object.{}".format(m.label), default=m.label) for m in self.inventory]

    def on_take_damage(self, battle, damage_params):
        pass

    def setup_other_attributes(self):
        self.inventory = {}
