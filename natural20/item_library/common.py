from natural20.item_library.object import Object
from typing import Optional
from natural20.concern.container import Container
import pdb

class StoneWall(Object):
    def __init__(self, map, properties):
        super().__init__(map, properties)

    def opaque(self, origin=None):
        return not self.dead()

    def passable(self, origin=None):
        return self.dead()

    def token(self):
        if self.dead():
            return ['`']
        else:
            return ['#']


class StoneWallDirectional(StoneWall):
    def __init__(self, map, properties):
        super().__init__(map, properties)
        self.wall_direction = self.properties['type']
        self.custom_border = self.properties.get('border')
        if self.custom_border:
            self.border = self.custom_border
        else:
            self.border = [0, # top
                        0, # right
                        0, # bottom
                        0] # left

            if self.wall_direction == 'stone_wall_tl':
                self.border = [1, 0, 0, 1]
            elif self.wall_direction == 'stone_wall_t':
                self.border = [1, 0, 0, 0]
            elif self.wall_direction == 'stone_wall_tr':
                self.border = [1, 1, 0, 0]
            elif self.wall_direction == 'stone_wall_r':
                self.border = [0, 1, 0, 0]
            elif self.wall_direction == 'stone_wall_br':
                self.border = [0, 1, 1, 0]
            elif self.wall_direction == 'stone_wall_b':
                self.border = [0, 0, 1, 0]
            elif self.wall_direction == 'stone_wall_bl':
                self.border = [0, 0, 1, 1]
            elif self.wall_direction == 'stone_wall_l':
                self.border = [0, 0, 0, 1]

    def token(self) -> Optional[str]:
        return self.properties.get('token')

    def passable(self, origin_pos = None):
        if origin_pos is None:
            return True

        pos_x, pos_y = self.map.position_of(self)
        if self.border[0] and origin_pos[1] < pos_y:
            return False
        if self.border[1] and origin_pos[0] > pos_x:
            return False
        if self.border[2] and origin_pos[1] > pos_y:
            return False
        if self.border[3] and origin_pos[0] < pos_x:
            return False
        return True

    def placeable(self, origin_pos = None):
        if origin_pos is None:
            return True

        pos_x, pos_y = self.map.position_of(self)
        if self.border[0] and origin_pos[1] < pos_y:
            return False
        if self.border[1] and origin_pos[0] > pos_x:
            return False
        if self.border[2] and origin_pos[1] > pos_y:
            return False
        if self.border[3] and origin_pos[0] < pos_x:
            return False
        return True

    def opaque(self, origin_pos = None):
        if origin_pos is None:
            return not self.dead()

        pos_x, pos_y = self.map.position_of(self)
        if self.border[0] and origin_pos[1] < pos_y:
            return not self.dead()
        if self.border[1] and origin_pos[0] > pos_x:
            return not self.dead()
        if self.border[2] and origin_pos[1] > pos_y:
            return not self.dead()
        if self.border[3] and origin_pos[0] < pos_x:
            return not self.dead()

        return self.dead()

    def wall(self, origin_pos = None):
        return True

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

    def opaque(self, origin=None):
        return False

    def passable(self, origin=None):
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
