"""Passive mechanics granted by worn/wielded magic items (item YAML keys).

An item only works while it is *active*: listed in the creature's
``equipped`` property and, when the item YAML sets
``requires_attunement: true``, attuned. Attunement is tracked by the optional
``attuned`` property (a list of item keys). Sheets without that property keep
the legacy behaviour where every equipped item counts as attuned.

Item YAML keys::

    ability_bonus: {wis: 2, max: 20}   # add to scores; ``max`` caps the result
    ability_set: {con: 19}             # score becomes this unless already higher
    proficiency_bonus: 1               # added to the proficiency bonus
    cannot_be_surprised: true          # never surprised
    regain_hp:                         # periodic healing while active
      amount: 15
      every_seconds: 3600              # campaign clock seconds between heals
      min_hp: 1                        # needs at least this many HP to work

``ability_set`` is applied before ``ability_bonus``; a bonus never lowers a
score that already exceeds its ``max``.

Without attunement an item gives only its nonmagical benefits (DMG): see
``effective_item_meta``, which drops ``magic_bonus`` / ``magical`` /
``additional_damage`` and applies the item's optional ``unattuned:`` overrides
(e.g. ``unattuned: {damage: 1d8}``). Managing attunement lives in
``natural20/utils/attunement.py``.
"""

from __future__ import annotations

ABILITY_KEYS = ('str', 'dex', 'con', 'int', 'wis', 'cha')

_ABILITY_ALIASES = {
    'strength': 'str', 'dexterity': 'dex', 'constitution': 'con',
    'intelligence': 'int', 'wisdom': 'wis', 'charisma': 'cha',
}

_CACHE_ATTR = '_item_mechanics_cache'


def _ability_key(name):
    key = str(name or '').strip().lower()
    key = _ABILITY_ALIASES.get(key, key)
    return key if key in ABILITY_KEYS else None


def _properties(entity):
    props = getattr(entity, '__dict__', {}).get('properties')
    return props if isinstance(props, dict) else None


def is_attuned(entity, item_key, item=None):
    """True when ``item_key`` needs no attunement or ``entity`` is attuned to it."""
    if item is None:
        session = getattr(entity, 'session', None)
        try:
            item = session.load_thing(item_key) if session is not None else None
        except Exception:
            item = None
    if not (item or {}).get('requires_attunement'):
        return True
    props = _properties(entity) or {}
    attuned = props.get('attuned')
    if attuned is None:
        return True
    return str(item_key) in [str(k) for k in attuned]


def item_key(meta):
    """Inventory key of an item dict (``_inventory_key`` / YAML ``id`` / sheet ``name``)."""
    if not isinstance(meta, dict):
        return None
    return meta.get('_inventory_key') or meta.get('id') or meta.get('name')


def magic_active(entity, meta, key=None):
    """True unless ``meta`` requires attunement that ``entity`` lacks."""
    if not isinstance(meta, dict) or not meta.get('requires_attunement'):
        return True
    if entity is None:
        return True
    key = key or item_key(meta)
    if key is None:
        return True
    return is_attuned(entity, key, meta)


def effective_item_meta(entity, meta, key=None):
    """``meta`` as ``entity`` can use it: the mundane form when not attuned."""
    if magic_active(entity, meta, key):
        return meta
    mundane = dict(meta)
    mundane['magic_bonus'] = 0
    mundane['magical'] = False
    mundane.pop('additional_damage', None)
    mundane['_unattuned'] = True
    overrides = meta.get('unattuned')
    if isinstance(overrides, dict):
        mundane.update(overrides)
    return mundane


def active_items(entity):
    """``[(item_key, item_yaml)]`` for equipped items that are currently working."""
    props = _properties(entity)
    if not props:
        return []
    equipped = props.get('equipped') or []
    if not equipped:
        return []
    session = getattr(entity, 'session', None)
    if session is None:
        return []
    out = []
    for key in equipped:
        try:
            item = session.load_thing(key)
        except Exception:
            item = None
        if not isinstance(item, dict):
            continue
        if not is_attuned(entity, key, item):
            continue
        out.append((key, item))
    return out


def _summary(entity):
    """Cached mechanics summary keyed on the equipped/attuned lists."""
    props = _properties(entity)
    if not props or not props.get('equipped'):
        return None
    attuned = props.get('attuned')
    key = (tuple(str(k) for k in props.get('equipped') or []),
           None if attuned is None else tuple(str(k) for k in attuned),
           id(getattr(entity, 'session', None)))
    cached = entity.__dict__.get(_CACHE_ATTR)
    if cached is not None and cached[0] == key:
        return cached[1]
    summary = {'set': {}, 'bonus': [], 'proficiency_bonus': 0,
               'cannot_be_surprised': False, 'regain_hp': []}
    for item_key, item in active_items(entity):
        for ability, value in (item.get('ability_set') or {}).items():
            ability = _ability_key(ability)
            if ability is None:
                continue
            summary['set'][ability] = max(int(value), summary['set'].get(ability, 0))
        bonus = item.get('ability_bonus') or {}
        if bonus:
            cap = bonus.get('max')
            for ability, value in bonus.items():
                ability = _ability_key(ability)
                if ability is None:
                    continue
                summary['bonus'].append((ability, int(value), None if cap is None else int(cap)))
        summary['proficiency_bonus'] += int(item.get('proficiency_bonus') or 0)
        if item.get('cannot_be_surprised'):
            summary['cannot_be_surprised'] = True
        regain = item.get('regain_hp')
        if isinstance(regain, dict) and int(regain.get('amount') or 0) > 0:
            summary['regain_hp'].append((str(item_key), regain))
    entity.__dict__[_CACHE_ATTR] = (key, summary)
    return summary


def ability_adjustments(entity):
    """``(set, bonus)`` ability changes from active items (empty when none)."""
    summary = _summary(entity)
    if not summary:
        return {}, []
    return summary['set'], summary['bonus']


class ItemAdjustedAbilityScores(dict):
    """Ability scores with item changes applied.

    Writes go through to the creature's base scores. ``copy.deepcopy`` returns
    the base scores so snapshots (Wild Shape) never bake item bonuses in.
    """

    def __init__(self, base, adjusted):
        super().__init__(adjusted)
        self._base = base

    def __setitem__(self, key, value):
        self._base[key] = value
        super().__setitem__(key, value)

    def __deepcopy__(self, memo):
        import copy
        return copy.deepcopy(dict(self._base), memo)

    def __reduce__(self):
        return (dict, (dict(self),))


def adjusted_ability_scores(entity, base):
    """``base`` scores with item ``ability_set`` / ``ability_bonus`` applied."""
    if not isinstance(base, dict):
        return base
    sets, bonuses = ability_adjustments(entity)
    if not sets and not bonuses:
        return base
    adjusted = dict(base)
    for ability, value in sets.items():
        current = adjusted.get(ability)
        if current is None or int(current) < value:
            adjusted[ability] = value
    for ability, value, cap in bonuses:
        current = adjusted.get(ability)
        if current is None:
            continue
        raised = int(current) + value
        if cap is not None:
            raised = max(int(current), min(raised, cap))
        adjusted[ability] = raised
    return ItemAdjustedAbilityScores(base, adjusted)


def item_proficiency_bonus(entity):
    summary = _summary(entity)
    return int(summary['proficiency_bonus']) if summary else 0


def cannot_be_surprised(entity):
    summary = _summary(entity)
    return bool(summary and summary['cannot_be_surprised'])


REGAIN_ANCHOR_ATTR = 'item_regain_hp_anchor'


def apply_item_regeneration(entity, game_time):
    """Heal ``entity`` for every full interval its ``regain_hp`` items were active."""
    summary = _summary(entity)
    attributes = getattr(entity, 'attributes', None)
    if not isinstance(attributes, dict):
        return 0
    if not summary or not summary['regain_hp']:
        attributes.pop(REGAIN_ANCHOR_ATTR, None)
        return 0
    anchors = attributes.setdefault(REGAIN_ANCHOR_ATTR, {})
    for stale in [k for k in anchors if k not in {key for key, _ in summary['regain_hp']}]:
        anchors.pop(stale, None)
    healed = 0
    game_time = int(game_time or 0)
    for item_key, spec in summary['regain_hp']:
        every = max(1, int(spec.get('every_seconds', 3600) or 3600))
        anchor = anchors.get(item_key)
        if anchor is None:
            anchors[item_key] = game_time
            continue
        intervals = (game_time - int(anchor)) // every
        if intervals <= 0:
            continue
        anchors[item_key] = int(anchor) + intervals * every
        try:
            if entity.dead() or entity.hp() is None or entity.hp() < int(spec.get('min_hp', 1)):
                continue
        except Exception:
            continue
        amount = int(spec['amount']) * intervals
        before = entity.hp()
        entity.heal(amount)
        gained = max(0, (entity.hp() or 0) - (before or 0))
        if gained:
            healed += gained
            session = getattr(entity, 'session', None)
            if session is not None:
                session.event_manager.received_event({
                    'event': 'item_regain_hp',
                    'source': entity,
                    'item': item_key,
                    'value': gained,
                })
    return healed


def tick_item_regeneration(session):
    """Called whenever the campaign clock advances."""
    registry = getattr(session, 'entity_registry', None)
    entities = getattr(registry, '_uid_to_entity', None)
    if not entities:
        return
    game_time = int(getattr(session, 'game_time', 0) or 0)
    for entity in list(entities.values()):
        props = _properties(entity)
        if not props or not props.get('equipped'):
            continue
        attributes = getattr(entity, 'attributes', None)
        summary = _summary(entity)
        if (summary and summary['regain_hp']) or (
                isinstance(attributes, dict) and attributes.get(REGAIN_ANCHOR_ATTR)):
            apply_item_regeneration(entity, game_time)
