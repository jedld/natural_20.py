"""Dancing weapons (SRD Dancing Sword and any item with a ``dancing`` block).

Item YAML::

    dancing:
      attacks: 4        # strikes before it flies back to the wielder
      move_feet: 30     # how far it flies per bonus action
      leash_feet: 30    # must stay within this distance of the wielder

While the item is equipped (and attuned, see ``natural20/utils/item_mechanics``)
the wielder can use a bonus action to toss it: it flies up to ``move_feet`` and
strikes a creature within 5 feet of where it stops, using the wielder's own
attack roll and damage. While it hovers, the same bonus action sends it on and
strikes again. After the last strike it returns to the wielder's hand, or drops
(into the wielder's inventory) when no hand is free. It falls if the wielder is
more than ``leash_feet`` away when commanded, and the wielder can catch it
(free) when adjacent or out of combat.

State lives in the wielder's ``properties['dancing_weapons']`` (saved with the
character); the map marker is a ``DancingWeaponTile`` found by uid.
"""
from __future__ import annotations

from natural20.action import Action
from natural20.actions.attack_action import AttackAction
from natural20.item_library.dancing_weapon_tile import DancingWeaponTile
from natural20.utils.class_feature_registry import register_class_feature

STATE_KEY = 'dancing_weapons'
DEFAULTS = {'attacks': 4, 'move_feet': 30, 'leash_feet': 30}


def dancing_spec(session, item_key):
    try:
        item = session.load_thing(item_key) if session is not None else None
    except Exception:
        item = None
    if not isinstance(item, dict):
        return None
    spec = item.get('dancing')
    if not spec:
        return None
    out = dict(DEFAULTS)
    if isinstance(spec, dict):
        out.update({k: int(v) for k, v in spec.items() if k in DEFAULTS and v is not None})
    out['name'] = item.get('name') or str(item_key).replace('_', ' ').title()
    out['image'] = item.get('image', item_key)
    return out


def dancing_state(entity):
    props = getattr(entity, 'properties', None)
    if not isinstance(props, dict):
        return {}
    return props.get(STATE_KEY) or {}


def ready_items(entity):
    """Equipped, attuned dancing items that are in hand (not hovering)."""
    from natural20.utils.item_mechanics import is_attuned
    session = getattr(entity, 'session', None)
    hovering = dancing_state(entity)
    out = []
    for key in (getattr(entity, 'properties', None) or {}).get('equipped') or []:
        if key in hovering or key in out:
            continue
        if dancing_spec(session, key) is None:
            continue
        if not is_attuned(entity, key):
            continue
        out.append(key)
    return out


def hovering_items(entity):
    return list(dancing_state(entity).keys())


def _map_for(entity, battle=None, battle_map=None):
    if battle_map is not None:
        return battle_map
    if battle is not None:
        try:
            return battle.map_for(entity)
        except Exception:
            return None
    return None


def _tile(battle_map, state):
    if battle_map is None or not state:
        return None
    uid = state.get('tile_uid')
    for obj in list(getattr(battle_map, 'interactable_objects', {}) or {}):
        if str(getattr(obj, 'entity_uid', '')) == str(uid):
            return obj
    return None


def _cheb(a, b):
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


def _has_free_hand(entity, item_key):
    session = entity.session
    try:
        item = entity._to_item(item_key, session.load_thing(item_key))
        return entity.used_hand_slots() + entity.hand_slots_required(item) <= 2.0
    except Exception:
        return True


class DancingWeaponAction(Action):
    """Toss, command or catch a dancing weapon (``mode``: toss | command | catch)."""

    def __init__(self, session, source, action_type='dancing_weapon', opts=None):
        opts = dict(opts or {})
        # The VTT rebuilds actions from ``action_type`` alone, so it carries
        # the mode and item: ``dancing_weapon:<mode>:<item>``.
        parts = str(action_type or '').split(':')
        if len(parts) == 3:
            opts.setdefault('mode', parts[1])
            opts.setdefault('item', parts[2])
        self.item_key = opts.get('item')
        self.mode = opts.get('mode', 'toss')
        if self.item_key and len(parts) != 3:
            action_type = f"dancing_weapon:{self.mode}:{self.item_key}"
        super().__init__(session, source, action_type, opts)
        self.target = None

    def clone(self):
        action = DancingWeaponAction(self.session, self.source, self.action_type,
                                     dict(self.opts or {}, item=self.item_key, mode=self.mode))
        action.target = self.target
        return action

    def to_h(self):
        data = super().to_h()
        data.update({'item': self.item_key, 'mode': self.mode})
        return data

    def _spec(self):
        return dancing_spec(self.session, self.item_key) or dict(DEFAULTS, name=self.item_key)

    def label(self):
        name = self._spec().get('name')
        if self.mode == 'catch':
            return f"Catch {name}"
        if self.mode == 'command':
            state = dancing_state(self.source).get(self.item_key) or {}
            return f"Command {name} ({int(state.get('attacks', 0))}/{self._spec()['attacks']} strikes)"
        return f"Toss {name}"

    def name(self):
        return self.label()

    def button_label(self):
        return self.label()

    def button_image(self):
        return self._spec().get('image') or f"dancing_weapon_{self.mode}"

    def __str__(self):
        return self.label()

    __repr__ = __str__

    # -- availability -------------------------------------------------
    @staticmethod
    def options_for(session, entity, battle=None):
        actions = []
        for key in ready_items(entity):
            actions.append(DancingWeaponAction(session, entity, 'dancing_weapon', {'item': key, 'mode': 'toss'}))
        for key in hovering_items(entity):
            actions.append(DancingWeaponAction(session, entity, 'dancing_weapon', {'item': key, 'mode': 'command'}))
            actions.append(DancingWeaponAction(session, entity, 'dancing_weapon', {'item': key, 'mode': 'catch'}))
        return actions

    @staticmethod
    def can(entity, battle, options=None):
        return any(a.available(battle) for a in DancingWeaponAction.options_for(entity.session, entity, battle))

    def available(self, battle=None):
        from natural20.utils.action_restrictions import is_restricted
        if self.mode == 'catch':
            if not _has_free_hand(self.source, self.item_key):
                return False
            if battle is None:
                return True
            battle_map = _map_for(self.source, battle)
            state = dancing_state(self.source).get(self.item_key)
            if battle_map is None or not state:
                return False
            try:
                return _cheb(battle_map.position_of(self.source), state['position']) <= 1
            except Exception:
                return False
        if battle is None or battle.entity_state_for(self.source) is None:
            return False
        if is_restricted(self.source, 'attack'):
            return False
        return self.source.has_bonus_action(battle)

    @staticmethod
    def auto_build(session, entity, battle, map=None):
        """Every reachable toss/command strike plus available catches (AI option lists)."""
        from natural20.utils.action_builder import acquire_targets
        battle_map = _map_for(entity, battle, map)
        out = []
        for option in DancingWeaponAction.options_for(session, entity, battle):
            if not option.available(battle):
                continue
            if option.mode == 'catch':
                if battle is None:
                    out.append(option)
                continue
            param = option.build_map()['param'][0]
            for target in acquire_targets(param, entity, battle, battle_map):
                if not hasattr(target, 'entity_uid') or target.dead():
                    continue
                if battle is not None and not battle.opposing(entity, target):
                    continue
                candidate = option.clone()
                candidate.target = target
                if candidate.reachable(battle_map):
                    out.append(candidate)
        return out

    @staticmethod
    def build(session, source):
        options = [a for a in DancingWeaponAction.options_for(session, source) if a.mode != 'catch']
        action = options[0] if options else DancingWeaponAction(session, source)
        return action.build_map()

    # -- targeting ----------------------------------------------------
    def build_map(self):
        if self.mode == 'catch':
            return self

        def set_target(target):
            action = self.clone()
            action.target = target
            return action

        spec = self._spec()
        return {
            'action': self,
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': spec['leash_feet'] + 5,
                'target_types': ['enemies'],
            }],
            'next': set_target,
        }

    def _origin(self, battle_map):
        if self.mode == 'command':
            state = dancing_state(self.source).get(self.item_key) or {}
            if state.get('position') is not None:
                return tuple(state['position'])
        return tuple(battle_map.position_of(self.source))

    def strike_square(self, battle_map, target=None):
        """Square the weapon flies to so ``target`` is within 5 feet, or ``None``."""
        target = target if target is not None else self.target
        if battle_map is None or target is None:
            return None
        spec = self._spec()
        fpg = battle_map.feet_per_grid
        move = spec['move_feet'] // fpg
        leash = spec['leash_feet'] // fpg
        origin = self._origin(battle_map)
        wielder = tuple(battle_map.position_of(self.source))
        squares = battle_map.entity_squares(target) or [battle_map.position_of(target)]
        squares = [tuple(sq) for sq in squares]
        best = None
        for sx, sy in squares:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    x, y = sx + dx, sy + dy
                    if (x, y) in squares:
                        continue
                    if x < 0 or y < 0 or x >= battle_map.size[0] or y >= battle_map.size[1]:
                        continue
                    if battle_map.wall(x, y):
                        continue
                    occupant = battle_map.entity_at(x, y)
                    if occupant is not None and occupant is not self.source:
                        continue
                    if _cheb((x, y), origin) > move or _cheb((x, y), wielder) > leash:
                        continue
                    rank = (_cheb((x, y), origin), occupant is self.source)
                    if best is None or rank < best[0]:
                        best = (rank, (x, y))
        return best[1] if best else None

    def validate(self, battle_map=None, target=None, battle=None):
        self.errors = []
        target = target if target is not None else self.target
        if self.mode == 'catch':
            return
        if target is None or not hasattr(target, 'entity_uid'):
            self.errors.append('Choose a creature for the weapon to strike.')
            return
        if self.strike_square(battle_map, target) is None:
            self.errors.append('The weapon cannot reach that creature.')

    def reachable(self, battle_map):
        return self.target is not None and self.strike_square(battle_map) is not None

    # -- resolution ---------------------------------------------------
    def resolve(self, session, map, opts=None):
        opts = opts or {}
        battle = opts.get('battle')
        battle_map = _map_for(self.source, battle, map)
        self.result = []
        spec = self._spec()
        state = dancing_state(self.source).get(self.item_key)
        base = {'source': self.source, 'item': self.item_key, 'item_name': spec['name'],
                'map': battle_map, 'battle': battle}

        if self.mode == 'catch':
            if state:
                self.result.append(dict(base, type='dancing_weapon_return', outcome='caught'))
            return self

        if self.mode == 'command':
            if not state or battle_map is None:
                return self
            wielder = battle_map.position_of(self.source)
            if _cheb(wielder, state['position']) * battle_map.feet_per_grid > spec['leash_feet']:
                self.result.append(dict(base, type='dancing_weapon_return', outcome='out_of_range',
                                        position=list(state['position'])))
                return self

        destination = self.strike_square(battle_map)
        if destination is None:
            return self
        attacks_made = int((state or {}).get('attacks', 0)) + 1
        self.result.append(dict(
            base, type='dancing_weapon_move', toss=self.mode == 'toss',
            target=self.target, to=list(destination),
            attack_number=attacks_made, max_attacks=spec['attacks'],
        ))

        attack = AttackAction(session, self.source, 'attack')
        attack.using = self.item_key
        attack.target = self.target
        attack._free_attack = True
        attack.resolve(session, battle_map, {'battle': battle, 'target': self.target})
        for item in attack.result:
            if isinstance(item, dict):
                item['_free_attack'] = True
                item['dancing_weapon'] = self.item_key
            self.result.append(item)

        if attacks_made >= spec['attacks']:
            self.result.append(dict(base, type='dancing_weapon_return', outcome='returned'))
        return self

    @staticmethod
    def apply(battle, item, session=None):
        kind = item.get('type')
        if kind not in ('dancing_weapon_move', 'dancing_weapon_return'):
            return
        source = item['source']
        if session is None:
            session = battle.session if battle is not None else source.session
        battle_map = item.get('map') or _map_for(source, battle)
        states = source.properties.setdefault(STATE_KEY, {})
        key = item['item']

        if kind == 'dancing_weapon_move':
            if battle is not None and battle.entity_state_for(source) is not None:
                battle.consume(source, 'bonus_action')
            state = states.get(key)
            if state is None:
                source.unequip(key, transfer_inventory=False)
                spec = dancing_spec(session, key) or {}
                tile = DancingWeaponTile(session, battle_map, source, key,
                                         item_name=item.get('item_name'), image=spec.get('image'))
                state = {'position': list(item['to']), 'attacks': 0, 'tile_uid': tile.entity_uid}
                states[key] = state
                if battle_map is not None:
                    battle_map.place_object(tile, *item['to'])
            else:
                tile = _tile(battle_map, state)
                if tile is not None:
                    battle_map.remove(tile)
                    battle_map.place_object(tile, *item['to'])
                state['position'] = list(item['to'])
            state['attacks'] = int(item.get('attack_number') or state.get('attacks', 0))
            session.event_manager.received_event({
                'event': 'dancing_weapon_move',
                'source': source,
                'target': item.get('target'),
                'to': item.get('to'),
                'toss': item.get('toss'),
                'item': key,
                'item_name': item.get('item_name'),
                'attack_number': item.get('attack_number'),
                'max_attacks': item.get('max_attacks'),
            })
            return

        state = states.pop(key, None)
        if not states:
            source.properties.pop(STATE_KEY, None)
        if state is None:
            return
        tile = _tile(battle_map, state)
        if tile is not None:
            battle_map.remove(tile)
        outcome = item.get('outcome', 'returned')
        if outcome in ('returned', 'caught') and _has_free_hand(source, key):
            source.properties.setdefault('equipped', []).append(key)
        else:
            if outcome == 'returned':
                outcome = 'no_free_hand'
            DancingWeaponAction._drop(source, key, battle_map, state.get('position'))
        session.event_manager.received_event({
            'event': 'dancing_weapon_return',
            'source': source,
            'item': key,
            'item_name': item.get('item_name'),
            'outcome': outcome,
        })

    @staticmethod
    def _drop(source, key, battle_map, position):
        """Leave the weapon on the ground where it fell (or with the wielder)."""
        from natural20.item_library.common import Ground
        if battle_map is not None and position is not None:
            try:
                ground = next((o for o in battle_map.objects_at(*position) if isinstance(o, Ground)), None)
            except Exception:
                ground = None
            if ground is not None:
                ground.add_item(key)
                return
        source.add_item(key)


def end_dancing(entity, battle_map=None, outcome='caught'):
    """Return every hovering weapon of ``entity`` to it (e.g. when combat ends)."""
    for key in hovering_items(entity):
        DancingWeaponAction.apply(None, {
            'type': 'dancing_weapon_return', 'source': entity, 'item': key,
            'item_name': (dancing_spec(entity.session, key) or {}).get('name'),
            'map': battle_map, 'outcome': outcome,
        }, entity.session)


register_class_feature(
    feature_id='dancing_weapon',
    action_class=DancingWeaponAction,
    provides=lambda entity: bool(ready_items(entity) or hovering_items(entity)),
    builder=lambda session, entity, feature_id: DancingWeaponAction.options_for(session, entity),
)
