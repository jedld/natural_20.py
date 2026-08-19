"""Wall-embedded windows (DoorObjectWall combo with glass/shutters, bars, and cover)."""
from natural20.item_library.door_object import DoorObjectWall, _entity_on_map
from natural20.utils.item_size import SIZE_ORDER, size_rank

_COVER_RANK = {
    'none': 0,
    'half': 1,
    'three_quarter': 2,
    'total': 3,
}

# Standing creatures of this size_identifier or smaller get total cover (PHB:
# a Tiny creature is fully hidden by a typical sill; Small at a slit).
_STANDING_TOTAL_COVER_MAX_SIZE = {
    'small': 1,   # tiny + small
    'medium': 0,  # tiny
    'large': -1,  # nobody standing
}

# Prone/"crouching" creatures of this size or smaller get total cover behind
# the wall under the opening (PHB total cover = completely concealed).
_PRONE_TOTAL_COVER_MAX_SIZE = {
    'small': 5,
    'medium': 3,  # large and smaller
    'large': 2,   # medium and smaller
}

_MAX_PASS_SIZE_ANY = frozenset({'any', 'all', 'none', 'unlimited', ''})

WINDOW_MATERIAL_STATS = {
    'glass': {'default_ac': 13, 'max_hp': 4, 'damage_threshold': 0},
    'wood': {'default_ac': 15, 'max_hp': 18, 'damage_threshold': 5},
    'stone': {'default_ac': 17, 'max_hp': 27, 'damage_threshold': 8},
    'iron': {'default_ac': 19, 'max_hp': 27, 'damage_threshold': 10},
}


def _as_edge_flags(value):
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        return [int(bool(v)) for v in value[:4]]
    try:
        index = int(value)
    except (TypeError, ValueError):
        return [0, 0, 0, 0]
    flags = [0, 0, 0, 0]
    if 0 <= index < 4:
        flags[index] = 1
    return flags


def _origin_crosses_edge(origin, pos, flags):
    if origin is None or pos is None or not flags:
        return False
    ox, oy = origin[0], origin[1]
    px, py = pos[0], pos[1]
    if flags[0] and oy < py:
        return True
    if flags[1] and ox > px:
        return True
    if flags[2] and oy > py:
        return True
    if flags[3] and ox < px:
        return True
    return False


class WindowObjectWall(DoorObjectWall):
    """Thin-wall window: open/close like a door, glass or opaque pane, inside bars."""

    def __init__(self, session, map, properties):
        props = properties if properties is not None else {}
        mat = str(props.get('window_material') or 'wood').strip().lower()
        stats = WINDOW_MATERIAL_STATS.get(mat)
        if stats:
            props.setdefault('default_ac', stats['default_ac'])
            props.setdefault('max_hp', stats['max_hp'])
            props.setdefault('damage_threshold', stats['damage_threshold'])
        super().__init__(session, map, props)
        self._init_window_attrs(props)

    def _init_window_attrs(self, properties=None):
        props = properties if properties is not None else (self.properties or {})
        pane = str(props.get('cover_pane') or props.get('pane') or 'glass').strip().lower()
        self.cover_pane = 'opaque' if pane in ('opaque', 'shutter', 'wood', 'solid') else 'glass'
        cover = str(props.get('inside_cover') or props.get('cover') or 'half').strip().lower()
        if cover in ('three_quarter', 'three-quarter', '3/4', 'three_quarters'):
            self.inside_cover = 'three_quarter'
        else:
            self.inside_cover = 'half'
        size = str(props.get('window_size') or 'medium').strip().lower()
        self.window_size = size if size in _STANDING_TOTAL_COVER_MAX_SIZE else 'medium'
        self.max_pass_size = self._normalize_max_pass_size(
            props.get('max_pass_size', props.get('passable_threshold'))
        )
        self.barred = bool(props.get('barred', False))
        if 'difficult_terrain' in props:
            self.difficult_terrain_through = bool(props.get('difficult_terrain'))
        else:
            self.difficult_terrain_through = True
        self.window_material = str(props.get('window_material') or 'wood').strip().lower()
        self.wall_material = str(props.get('wall_material') or 'stone').strip().lower()
        if not self.properties.get('lockable') and 'key' not in self.properties:
            self.lockable = False

    @staticmethod
    def _normalize_max_pass_size(value):
        if value is None:
            return 'any'
        text = str(value).strip().lower()
        if text in _MAX_PASS_SIZE_ANY:
            return 'any'
        if text in SIZE_ORDER:
            return text
        return 'any'

    def kind_of_door(self):
        return self.properties.get('kind_of_door', True)

    def kind_of_window(self):
        return True

    def label(self):
        if self.properties.get('label'):
            return self.properties.get('label')
        state = 'Opened' if self.opened() else 'Closed'
        pane = 'glass' if self.cover_pane == 'glass' else 'shuttered'
        barred = ', barred' if self.barred and self.closed() else ''
        return f"{state} {pane} window{barred}"

    def description(self):
        return self.properties.get('description', 'A window set into the wall')

    def _opening_flags(self):
        return _as_edge_flags(self.door_pos)

    def _crosses_opening(self, origin, pos=None):
        if pos is None:
            if not self.map:
                return False
            pos = self.map.position_of(self)
        return _origin_crosses_edge(origin, pos, self._opening_flags())

    def _window_blocks_vision(self):
        if self.dead() or self.opened():
            return False
        return self.cover_pane != 'glass'

    def opaque(self, origin=None):
        from natural20.item_library.common import StoneWallDirectional

        if origin is None:
            return (not self.dead()) and self._window_blocks_vision()

        pos = self.map.position_of(self)
        if self._crosses_opening(origin, pos):
            return self._window_blocks_vision()
        return StoneWallDirectional.opaque(self, origin=origin)

    def passable(self, origin_pos=None):
        return DoorObjectWall.passable(self, origin_pos)

    def passable_for(self, entity, origin_pos=None):
        """Passability when a specific creature tries to cross the opening."""
        if not self.passable(origin_pos):
            return False
        if entity is None or origin_pos is None:
            return True
        if not self._crosses_opening(origin_pos):
            return True
        return not self._entity_too_large_to_pass(entity)

    def _entity_too_large_to_pass(self, entity):
        if self.max_pass_size == 'any':
            return False
        return self._occupant_size_id(entity) > size_rank(self.max_pass_size, default='gargantuan')

    def pass_size_tooltip(self):
        if not self.max_pass_size or self.max_pass_size == 'any':
            return None
        cap = self.max_pass_size.title()
        if self.max_pass_size == 'tiny':
            return 'Fits Tiny creatures only'
        return f'Fits {cap} or smaller'

    def terrain_tooltip_details(self):
        line = self.pass_size_tooltip()
        return [line] if line else []

    def movement_cost(self):
        # Crossing cost is directional — see movement_cost_from. Standing on the
        # window cell without crossing the opening is not difficult terrain.
        return super().movement_cost()

    def movement_cost_from(self, origin_pos=None, dest_pos=None):
        if not self.opened() or self.dead() or not self.difficult_terrain_through:
            return 1
        win_pos = None
        if self.map:
            try:
                win_pos = self.map.position_of(self)
            except Exception:
                win_pos = None
        if origin_pos is None or win_pos is None:
            return 1
        dest = dest_pos if dest_pos is not None else win_pos
        origin_out = self._crosses_opening(origin_pos, win_pos)
        dest_out = self._crosses_opening(dest, win_pos)
        if origin_out != dest_out:
            return 2
        return 1

    def _occupant_size_id(self, occupant):
        fn = getattr(occupant, 'size_identifier', None)
        if callable(fn):
            try:
                return int(fn())
            except Exception:
                return 2
        return 2

    def _occupant_is_prone(self, occupant):
        fn = getattr(occupant, 'prone', None)
        if callable(fn):
            try:
                return bool(fn())
            except Exception:
                return False
        return bool(getattr(occupant, 'prone', False))

    def _occupant_on_inside(self, occupant, origin):
        """True when the protected creature is on the interior side of the opening."""
        if occupant is None or not self.map:
            return True
        try:
            occ_pos = self.map.position_of(occupant)
        except Exception:
            return True
        win_pos = self.map.position_of(self)
        if occ_pos is None or win_pos is None:
            return True
        if tuple(occ_pos) == tuple(win_pos):
            return True
        # Across the opening from this cell → outside.
        if self._crosses_opening(occ_pos, win_pos):
            return False
        return True

    def _open_cover_for(self, occupant):
        size_id = self._occupant_size_id(occupant) if occupant is not None else 2
        prone = self._occupant_is_prone(occupant) if occupant is not None else False
        if prone and size_id <= _PRONE_TOTAL_COVER_MAX_SIZE.get(self.window_size, 3):
            return 'total'
        if size_id <= _STANDING_TOTAL_COVER_MAX_SIZE.get(self.window_size, 0):
            return 'total'
        return self.inside_cover

    def cover_across(self, from_pos, to_pos, occupant=None):
        """Cover granted when a line of sight crosses this window's opening."""
        if self.dead():
            return 'none'
        pos = None
        if self.map:
            try:
                pos = self.map.position_of(self)
            except Exception:
                pos = None
        if pos is None:
            return 'none'
        crosses = self._crosses_opening(from_pos, pos) or self._crosses_opening(to_pos, pos)
        if not crosses:
            # Also true when the ray steps from this cell across the opening.
            if from_pos is not None and tuple(from_pos) == tuple(pos) and self._crosses_opening(to_pos, pos):
                crosses = True
            elif to_pos is not None and tuple(to_pos) == tuple(pos) and self._crosses_opening(from_pos, pos):
                crosses = True
        if not crosses:
            return 'none'

        if self.closed():
            return 'total'

        if occupant is not None and not self._occupant_on_inside(occupant, from_pos):
            return 'none'
        return self._open_cover_for(occupant)

    def cover_blocks_vision_across(self, from_pos, to_pos, occupant=None):
        level = self.cover_across(from_pos, to_pos, occupant)
        if level != 'total':
            return False
        if self.closed() and self.cover_pane == 'glass':
            return False
        return True

    def half_cover(self):
        return False

    def three_quarter_cover(self):
        return False

    def total_cover(self):
        return False

    def cover_ac(self):
        return 0

    def _entity_is_inside(self, entity, admin=False):
        if admin or not entity or not self.map:
            return True
        if not _entity_on_map(self.map, entity):
            return False
        try:
            ex, ey = self.map.position_of(entity)
            dx, dy = self.map.position_of(self)
        except Exception:
            return False
        if (ex, ey) == (dx, dy):
            return True
        return not self._crosses_opening((ex, ey), (dx, dy))

    def available_interactions(self, entity, battle=None, admin=False):
        if self.dead():
            return {}
        if self.concealed() and not admin:
            return {}
        if entity and not admin and not _entity_on_map(self.map, entity):
            return {}

        actions = {}
        inside = self._entity_is_inside(entity, admin=admin)

        def in_open_range():
            if admin:
                return True
            if not entity:
                return False
            try:
                ex, ey = self.map.position_of(entity)
                dx, dy = self.map.position_of(self)
            except Exception:
                return False
            if (ex, ey) == (dx, dy):
                return True
            return abs(ex - dx) + abs(ey - dy) == 1

        if not in_open_range():
            return actions

        if self.opened():
            actions['close'] = {
                'disabled': self.someone_blocking_the_doorway(),
                'disabled_text': 'object.window.window_blocked',
            }
        else:
            open_disabled = self.barred and not inside and not admin
            actions['open'] = {
                'disabled': open_disabled,
                'disabled_text': 'object.window.barred' if open_disabled else None,
            }

        if inside or admin:
            if self.barred:
                actions['unbar'] = {}
            elif self.closed():
                actions['bar'] = {}

        if self.lockable:
            door_actions = DoorObjectWall.available_interactions(self, entity, battle, admin=admin)
            for key in ('unlock', 'lock', 'lockpick'):
                if key in door_actions:
                    actions[key] = door_actions[key]
        return actions

    def resolve(self, entity, action, other_params, opts=None):
        if action in ('bar', 'unbar'):
            return {'action': action}
        return super().resolve(entity, action, other_params, opts)

    def use(self, entity, result, session=None):
        action = (result or {}).get('action')
        results = []
        if action == 'bar':
            if self.closed() and not self.barred:
                self.barred = True
                if session:
                    session.event_manager.received_event({
                        'source': entity,
                        'target': self,
                        'event': 'object_interaction',
                        'sub_type': 'bar',
                        'result': 'success',
                        'reason': 'object.window.bar',
                    })
            return results
        if action == 'unbar':
            if self.barred:
                self.barred = False
                if session:
                    session.event_manager.received_event({
                        'source': entity,
                        'target': self,
                        'event': 'object_interaction',
                        'sub_type': 'unbar',
                        'result': 'success',
                        'reason': 'object.window.unbar',
                    })
            return results
        if action == 'open' and self.barred:
            inside = self._entity_is_inside(entity, admin=bool(getattr(entity, 'is_admin', False)))
            if not inside:
                if session:
                    session.event_manager.received_event({
                        'source': entity,
                        'target': self,
                        'event': 'object_interaction',
                        'sub_type': 'open_failed',
                        'result': 'failed',
                        'reason': 'object.window.barred',
                    })
                return results
            self.barred = False
        return super().use(entity, result, session)

    def update_state(self, state):
        if state == 'barred':
            self.barred = True
            if self.opened():
                self.close()
            return
        if state == 'unbarred':
            self.barred = False
            return
        super().update_state(state)

    def to_dict(self):
        data = super().to_dict()
        data['cover_pane'] = self.cover_pane
        data['inside_cover'] = self.inside_cover
        data['window_size'] = self.window_size
        data['max_pass_size'] = self.max_pass_size
        data['barred'] = self.barred
        data['difficult_terrain_through'] = self.difficult_terrain_through
        data['window_material'] = self.window_material
        data['wall_material'] = self.wall_material
        return data

    @staticmethod
    def from_dict(data):
        session = data['session']
        window = WindowObjectWall(session, None, data['properties'])
        window.entity_uid = data['entity_uid']
        window.door_pos = data.get('door_pos', window.door_pos)
        window.window = data.get('window', window.window)
        window.is_secret = data.get('secret', window.is_secret)
        window.front_direction = data.get('front_direction', window.front_direction)
        window.privacy_lock = data.get('privacy_lock', window.privacy_lock)
        window.door_blocking = data.get('door_blocking', window.door_blocking)
        window.state = data.get('state', window.state)
        window.lockable = data.get('lockable', window.lockable)
        window.locked = data.get('locked', window.locked)
        window.key_name = data.get('key', window.key_name)
        window.border = data.get('border', window.border)
        window.wall_direction = data.get('wall_direction', window.wall_direction)
        window.custom_border = data.get('custom_border', window.custom_border)
        window.cover_pane = data.get('cover_pane', window.cover_pane)
        window.inside_cover = data.get('inside_cover', window.inside_cover)
        window.window_size = data.get('window_size', window.window_size)
        window.max_pass_size = WindowObjectWall._normalize_max_pass_size(
            data.get('max_pass_size', window.max_pass_size)
        )
        window.barred = data.get('barred', window.barred)
        window.difficult_terrain_through = data.get(
            'difficult_terrain_through', window.difficult_terrain_through
        )
        window.window_material = data.get('window_material', window.window_material)
        window.wall_material = data.get('wall_material', window.wall_material)
        return window
