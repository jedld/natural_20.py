from natural20.item_library.object import Object
from typing import Optional
from natural20.concern.container import Container
from natural20.concern.lootable import Lootable
import pdb

class StoneWall(Object):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties)

    def opaque(self, origin=None):
        return not self.dead()

    def passable(self, origin=None):
        return self.dead()

    def token(self):
        if self.dead():
            return ['`']
        else:
            return ['#']
        
    def to_dict(self):
        hash = super().to_dict()
        hash['session'] = self.session
        hash['entity_uid'] = self.entity_uid
        return hash
    
    def from_dict(data):
        session = data['session']
        wall = StoneWall(session, None, data['properties'])
        wall.entity_uid = data['entity_uid']
        return wall

class StoneWallDirectional(StoneWall):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties)
        self.wall_direction = self.properties['type']
        self.custom_border = self.properties.get('border')
        self.window = self.properties.get('window', [0, 0, 0, 0])

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

    def to_dict(self):
        hash = super().to_dict()
        hash['session'] = self.session
        hash['wall_direction'] = self.wall_direction
        hash['custom_border'] = self.custom_border
        hash['border'] = self.border
        hash['window'] = self.window
        return hash
    
    def from_dict(data):
        session = data['session']
        wall = StoneWallDirectional(session, None, data['properties'])
        wall.entity_uid = data['entity_uid']
        wall.wall_direction = data['wall_direction']
        wall.custom_border = data['custom_border']
        wall.border = data['border']
        wall.window = data['window']
        return wall
        
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

    def opaque(self, origin=None):
        pos_x, pos_y = self.map.position_of(self)
        if origin is None:
            return not self.dead()

        window_ok = (
            (not self.window[0] or origin[1] >= pos_y) and
            (not self.window[1] or origin[0] <= pos_x) and
            (not self.window[2] or origin[1] <= pos_y) and
            (not self.window[3] or origin[0] >= pos_x)
        )

        border_toggled = any([
            self.border[0] and origin[1] < pos_y,
            self.border[1] and origin[0] > pos_x,
            self.border[2] and origin[1] > pos_y,
            self.border[3] and origin[0] < pos_x,
        ])

        opaqueness = (not self.dead()) if border_toggled else self.dead()
        return opaqueness and window_ok

    def wall(self, origin_pos = None):
        return True

class Ground(Object, Container, Lootable):
    def __init__(self, session, map, properties):
        super().__init__(session, map, properties)
        self.state = self.properties.get('state', 'open')
        self.locked = None
        self.key_name = None

    def opaque(self, origin=None):
        return False

    def passable(self, origin=None):
        return True

    def placeable(self):
        return True

    def token(self):
        return ["·"]

    def color(self):
        return 'cyan'

    def build_map(self, action, action_object):
        if action == 'pickup_drop':
            def next_action(items):
                action_object.other_params = items
                return action_object
            return {
                'action': action_object,
                'param': [{
                    'type': 'select_items',
                    'mode': 'transfer',
                    'label': action_object.source.items_label(),
                    'items': action_object.source.inventory
                }],
                'next': next_action
            }

    def available_interactions(self, entity, battle=None, admin=False):
        interactions = {}
        if self.map.position_of(entity) == self.map.position_of(self):
            if len(self.inventory) > 0 or len(entity.inventory) > 0:
                interactions['pickup_drop'] = {}
        return interactions

    def interactable(self, entity=None):
        return True

    def resolve(self, entity, action, other_params, opts=None):
        if opts is None:
            opts = {}

        if action is None:
            return

        if action == 'pickup_drop':
            return {
                'action': action,
                'items': other_params,
                'source': entity,
                'target': self,
                'battle': opts.get('battle')
            }

    def use(self, entity, result):
         if result['action'] == 'pickup_drop':
            self.transfer(result['battle'], result['source'], result['target'], result['items'])

    def on_take_damage(self, battle, damage_params):
        pass

    def setup_other_attributes(self):
        self.inventory = {}

    def to_dict(self):
        h_dict = super().to_dict()
        h_dict['session'] = self.session
        h_dict['inventory'] = self.inventory
        return h_dict


    def from_dict(data):
        session = data['session']
        ground = Ground(session, None, data['properties'])
        ground.entity_uid = data['entity_uid']
        return ground
