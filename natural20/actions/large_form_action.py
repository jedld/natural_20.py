"""Large Form (Goliath, SRD 5.2; character level 5+).

Bonus action: become Large for 10 minutes if there is room. While Large the
creature has advantage on Strength checks and +10 ft speed. Once per long
rest (``large_form`` uses pool).
"""

from __future__ import annotations

from natural20.action import Action
from natural20.utils import giant_ancestry


LARGE_FORM_DURATION_SECONDS = 600
LARGE_FORM_SPEED_BONUS = 10
_SIZE_ORDER = ['tiny', 'small', 'medium', 'large', 'huge', 'gargantuan']


def _clear_footprint(battle_map, entity):
    """Clear every token cell this entity occupies around its anchor."""
    pos = battle_map.position_of(entity)
    if pos is None:
        return None
    x, y = pos
    for px in range(x, min(battle_map.size[0], x + 4)):
        for py in range(y, min(battle_map.size[1], y + 4)):
            cell = battle_map.tokens[px][py]
            if cell and cell['entity'] is entity:
                battle_map.tokens[px][py] = None
    return x, y


def _restamp(battle_map, entity, anchor=None):
    """Re-place ``entity``'s token so its footprint matches its current size."""
    pos = _clear_footprint(battle_map, entity)
    if pos is None:
        return
    battle_map.place(anchor or pos, entity)


class LargeFormEffect:
    """Size, speed and Strength-check bonus while in Large Form."""

    def __init__(self, source):
        self.source = source
        self.id = f"large_form:{id(self)}"
        self._map = None

    def __str__(self):
        return 'large_form'

    def size_override(self, entity, opt=None):
        return 'large'

    def speed_override(self, entity, opt=None):
        value = (opt or {}).get('value') or 0
        return value + LARGE_FORM_SPEED_BONUS

    def dismiss(self, entity, _descriptor=None, _opts=None):
        battle_map = getattr(self, '_map', None)
        if battle_map is None:
            try:
                battle_map = entity.session.map_for(entity)
            except Exception:
                battle_map = None
        if battle_map is not None and entity in getattr(battle_map, 'entities', {}):
            _restamp(battle_map, entity)
        try:
            entity.session.event_manager.received_event({'event': 'large_form_end', 'source': entity})
        except Exception:
            pass


def _large_anchor(battle_map, entity, battle=None):
    """Anchor square where a Large footprint covering ``entity``'s square fits."""
    try:
        x, y = battle_map.position_of(entity)
    except Exception:
        return None
    probe = LargeFormEffect(entity)
    entity.register_effect('size_override', probe, effect=probe)
    try:
        for ax, ay in ((x, y), (x - 1, y), (x, y - 1), (x - 1, y - 1)):
            if ax < 0 or ay < 0 or ax + 1 >= battle_map.size[0] or ay + 1 >= battle_map.size[1]:
                continue
            if battle_map.placeable(entity, ax, ay, battle, squeeze=False):
                return ax, ay
        return None
    finally:
        entity.effects['size_override'] = [
            d for d in entity.effects.get('size_override', []) if d.get('effect') is not probe
        ]


class LargeFormAction(Action):
    FEATURE = 'large_form'

    def __init__(self, session, source, action_type='large_form', opts=None):
        super().__init__(session, source, action_type, opts)
        self.as_bonus_action = True

    def label(self):
        return 'Large Form'

    def button_label(self):
        return self.label()

    def __str__(self):
        return "LargeForm"

    __repr__ = __str__

    @staticmethod
    def can(entity, battle, options=None):
        if not giant_ancestry.has_use(entity, LargeFormAction.FEATURE):
            return False
        if giant_ancestry.large_form_active(entity):
            return False
        size = str(entity.size() or 'medium').lower()
        if size in _SIZE_ORDER and _SIZE_ORDER.index(size) >= _SIZE_ORDER.index('large'):
            return False
        if battle is not None and battle.entity_state_for(entity) is not None:
            if entity.total_bonus_actions(battle) <= 0:
                return False
            battle_map = battle.map_for(entity)
            if battle_map is not None and _large_anchor(battle_map, entity, battle) is None:
                return False
        return True

    def build_map(self):
        return self

    @classmethod
    def build(cls, session, source):
        return cls(session, source).build_map()

    def resolve(self, session, map, opts=None):
        battle = (opts or {}).get('battle')
        battle_map = map or (battle.map_for(self.source) if battle else None)
        anchor = None
        if battle_map is not None:
            anchor = _large_anchor(battle_map, self.source, battle)
            if anchor is None:
                self.result = []
                return self
        self.result = [{
            'type': 'large_form',
            'source': self.source,
            'battle': battle,
            'map': battle_map,
            'anchor': list(anchor) if anchor else None,
            'refresh_map': True,
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'large_form':
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle else source.session
        if battle is not None:
            battle.consume(source, 'bonus_action')
        giant_ancestry.spend_use(source, LargeFormAction.FEATURE)

        effect = LargeFormEffect(source)
        battle_map = item.get('map')
        effect._map = battle_map
        source.register_effect('size_override', effect, effect=effect, source=source,
                               duration=LARGE_FORM_DURATION_SECONDS)
        source.register_effect('speed_override', effect, effect=effect, source=source,
                               duration=LARGE_FORM_DURATION_SECONDS)
        if battle is not None:
            state = battle.entity_state_for(source)
            if state is not None:
                state['movement'] = state.get('movement', 0) + LARGE_FORM_SPEED_BONUS
        if battle_map is not None and item.get('anchor'):
            _restamp(battle_map, source, tuple(item['anchor']))
        session.event_manager.received_event({'event': 'large_form', 'source': source})
        return item
