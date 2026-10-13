"""Polymorph-style beast forms (SRD *Polymorph*; reusable by similar effects).

The target's game statistics, including mental ability scores, are replaced
by a beast statblock from ``npcs/<beast>.yml``. It keeps its hit points in
the new form; when the form drops to 0 HP it reverts and excess damage
carries over to the normal form (handled in ``Entity.take_damage``). The form
also ends when the caster's concentration ends.

Player characters reuse the Wild Shape overlay (``_wild_shape_state`` with
``source='polymorph'``) so beast attacks, AC and speed are already wired.
NPCs snapshot their statblock keys into ``properties['polymorph_state']``,
which persists with the NPC's properties for save/load.
"""

import copy

from natural20.entity_class import wild_shape as ws

STATE_KEY = 'polymorph_state'
STATUS = 'polymorphed'

# Action types a beast form keeps: no spells, speech, item use, or class /
# monster features.
ALLOWED_ACTION_TYPES = frozenset({
    'attack', 'move', 'dash', 'disengage', 'dodge', 'hide', 'help', 'ready',
    'look', 'grapple', 'escape_grapple', 'drop_grapple', 'shove', 'push',
    'stand', 'prone',
})

# NPC statblock keys replaced by (or removed for) the beast form.
NPC_STAT_KEYS = (
    'ability', 'ability_scores', 'max_hp', 'hp_die', 'default_ac', 'speed',
    'speed_fly', 'speed_swim', 'speed_climb', 'size', 'race', 'kind', 'cr',
    'resistances', 'damage_resistances', 'immunities', 'damage_immunities',
    'vulnerabilities', 'damage_vulnerabilities', 'condition_immunities',
    'attributes', 'actions', 'multiattack', 'legendary_actions',
    'legendary_action_count', 'legendary_resistance', 'regeneration',
    'misty_escape', 'summons', 'spell_slots', 'prepared_spells', 'spells',
    'spell_ability', 'spellcasting_ability', 'spellcaster_level',
    'saving_throw_proficiencies', 'skills', 'darkvision', 'passive_perception',
    'token', 'token_image', 'reactions', 'bonus_actions', 'traits',
)


def _is_pc(entity):
    return hasattr(entity, 'is_wild_shaped') and not entity.npc()


def is_polymorphed(entity):
    if entity is None:
        return False
    if ws.is_wild_shaped(entity) and ws.form_source(entity) == 'polymorph':
        return True
    props = getattr(entity, 'properties', None) or {}
    return bool(props.get(STATE_KEY))


def has_assumed_form(entity):
    """Any beast form whose 0 HP reverts instead of downing the creature."""
    return ws.is_wild_shaped(entity) or is_polymorphed(entity)


def current_form(entity):
    if ws.is_wild_shaped(entity):
        return ws.current_form(entity)
    state = (getattr(entity, 'properties', None) or {}).get(STATE_KEY)
    return state.get('form') if state else None


def polymorphed_by_side_of(target, entity, battle) -> bool:
    """*target* is held in a Polymorph cast by *entity* or one of its allies.
    Damaging the beast form only ends that control early."""
    if not is_polymorphed(target):
        return False
    uid = (_state(target) or {}).get('caster_uid')
    if not uid:
        return False
    if uid == getattr(entity, 'entity_uid', None):
        return True
    try:
        caster = battle.entity_by_uid(uid) if battle is not None else None
        return caster is not None and battle.allies(entity, caster)
    except Exception:
        return False


def _state(entity):
    if ws.is_wild_shaped(entity):
        return entity._wild_shape_state
    return (getattr(entity, 'properties', None) or {}).get(STATE_KEY)


def creature_level(entity):
    """CR for monsters, character level for PCs (the Polymorph form cap)."""
    props = getattr(entity, 'properties', None) or {}
    if entity.npc() and props.get('cr') is not None:
        try:
            return float(props['cr'])
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(entity.level())
    except Exception:
        return 0.0


def beast_cr(props):
    try:
        return float(props.get('cr') or 0)
    except (TypeError, ValueError):
        return 0.0


def unaffected_reason(target):
    """Return why Polymorph has no effect on ``target`` (or None)."""
    if target is None:
        return 'no_target'
    if target.hp() <= 0 or target.dead():
        return 'zero_hp'
    race = (getattr(target, 'properties', None) or {}).get('race') or []
    if 'shapechanger' in ([race] if isinstance(race, str) else race):
        return 'shapechanger'
    if is_polymorphed(target):
        return 'already_polymorphed'
    return None


def load_beast(session, beast_id):
    return ws._load_beast_yaml(session, beast_id)


def transform(target, beast_id, *, caster=None, effect=None, battle=None):
    """Turn ``target`` into ``beast_id``. Returns the beast props."""
    session = target.session
    props = load_beast(session, beast_id)
    meta = {
        'caster_uid': getattr(caster, 'entity_uid', None),
        'effect_id': getattr(effect, 'id', None),
    }
    if _is_pc(target):
        ws.assume_form(target, beast_id, props, source='polymorph', replace_mental=True, meta=meta)
    else:
        _npc_assume_form(target, beast_id, props, meta)
    if STATUS not in target.statuses:
        target.statuses.append(STATUS)
    target.drop_grapple()
    session.event_manager.received_event({
        'source': target,
        'event': 'polymorph',
        'form': beast_id,
        'caster': caster,
    })
    return props


def revert(target, *, battle=None, reason=None, end_spell=True):
    """Restore ``target``'s normal form. No-op when not polymorphed."""
    if not is_polymorphed(target):
        return False
    state = copy.deepcopy(_state(target)) or {}
    if _is_pc(target):
        ws.revert(target, overflow_damage=0, battle=None)
    else:
        _npc_revert(target)
    if STATUS in target.statuses:
        target.statuses.remove(STATUS)
    target.session.event_manager.received_event({
        'source': target,
        'event': 'polymorph_end',
        'form': state.get('form'),
        'reason': reason,
    })
    if end_spell:
        _end_caster_spell(target, state)
    return True


def end_assumed_form(entity, *, battle=None, reason='dropped_to_zero'):
    """End whatever beast form ``entity`` holds (from ``Entity.take_damage``)."""
    if is_polymorphed(entity):
        return revert(entity, battle=battle, reason=reason)
    if ws.is_wild_shaped(entity):
        ws.revert(entity, overflow_damage=0, battle=None)
        entity.session.event_manager.received_event({
            'source': entity,
            'event': 'wild_shape_revert',
            'reason': 'beast_dropped',
        })
        return True
    return False


def _end_caster_spell(target, state):
    caster_uid = state.get('caster_uid')
    effect_id = state.get('effect_id')
    if not caster_uid:
        return
    caster = target.session.entity_by_uid(caster_uid)
    if caster is None:
        return
    for entry in list(getattr(caster, 'casted_effects', []) or []):
        effect = entry.get('effect')
        if getattr(effect, 'id', None) == effect_id or (
                effect_id is None and entry.get('target') is target):
            caster.dismiss_effect(effect)
            return


def filter_actions(entity, actions):
    """Drop actions a polymorphed creature cannot take."""
    if not is_polymorphed(entity):
        return actions
    return [a for a in actions if getattr(a, 'action_type', a) in ALLOWED_ACTION_TYPES]


# -- NPC overlay ---------------------------------------------------------

def _sync_npc_runtime(npc):
    from natural20.npc import _normalize_damage_traits

    props = npc.properties
    npc.ability_scores = props.get('ability') or props.get('ability_scores') or {}
    npc.npc_actions = props.get('actions', []) or []
    npc.legendary_actions = props.get('legendary_actions', []) or []
    npc.resistances = _normalize_damage_traits(
        props.get('resistances', props.get('damage_resistances', [])))
    npc.damage_vulnerabilities = _normalize_damage_traits(
        props.get('damage_vulnerabilities', props.get('vulnerabilities', [])))
    npc.damage_immunities = _normalize_damage_traits(
        props.get('damage_immunities', props.get('immunities', [])))
    npc.condition_immunities = props.get('condition_immunities', []) or []
    npc.flying = bool(props.get('speed_fly'))


def _npc_assume_form(npc, beast_id, beast, meta):
    props = npc.properties
    snapshot = {
        'properties': {k: copy.deepcopy(props[k]) for k in NPC_STAT_KEYS if k in props},
        'max_hp': npc._max_hp,
        'hp': npc.attributes.get('hp'),
    }
    for key in NPC_STAT_KEYS:
        if key in beast:
            props[key] = copy.deepcopy(beast[key])
        else:
            props.pop(key, None)
    if not props.get('token_image'):
        props['token_image'] = f"token_{beast.get('kind') or beast_id}.png".replace(' ', '_').lower()
    props[STATE_KEY] = {'form': beast_id, 'snapshot': snapshot, **meta}

    _sync_npc_runtime(npc)
    beast_hp = int(beast.get('max_hp') or 1)
    npc._max_hp = beast_hp
    npc.attributes['hp'] = beast_hp


def _npc_revert(npc):
    props = npc.properties
    state = props.pop(STATE_KEY, None) or {}
    snapshot = state.get('snapshot') or {}
    saved = snapshot.get('properties') or {}
    for key in NPC_STAT_KEYS:
        if key in saved:
            props[key] = copy.deepcopy(saved[key])
        else:
            props.pop(key, None)
    _sync_npc_runtime(npc)
    if snapshot.get('max_hp') is not None:
        npc._max_hp = snapshot['max_hp']
    if snapshot.get('hp') is not None:
        npc.attributes['hp'] = snapshot['hp']


def reapply_after_load(npc):
    """Restore NPC runtime fields from a persisted beast-form statblock."""
    if (getattr(npc, 'properties', None) or {}).get(STATE_KEY):
        _sync_npc_runtime(npc)
