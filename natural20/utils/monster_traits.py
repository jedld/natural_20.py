"""SRD monster traits: Legendary Resistance, Regeneration and Misty Escape.

NPC YAML keys (all optional)::

    legendary_resistance: 3          # uses per day; or list it under `attributes`
    legendary_resistance_policy:     # when to burn a use on a concentration check
      concentration: auto            # auto | always | never
      concentration_min_level: 3     # auto: only protect spells of this level or higher
      concentration_reserve: 1       # auto: uses always kept back for real saves
    regeneration:
      hp: 20                         # regained at the start of the creature's turn
      suppressed_by: [radiant]       # damage types that stop it at its next turn start
      blocked_by: [sunlight, running_water]
    misty_escape:
      blocked_by: [sunlight, running_water]   # destroyed instead of turning to mist
      coffin:                        # optional resting place; omit = reached off-map
        map: castle_crypt
        position: [4, 7]
      recovery_seconds: 3600         # time in the coffin before regaining 1 HP

Environment helpers: a creature is *in sunlight* when it has the
``in_sunlight`` status, its map sets ``sunlight: true``, or the map sets
``sunlight: day`` and the campaign clock is not night. It is *in running water*
with the ``in_running_water`` status or when standing on a square listed in the
map's ``running_water_squares``.
"""

from __future__ import annotations

DEFAULT_LEGENDARY_RESISTANCE_USES = 3

MIST_FORM_STATUS = 'mist_form'


def _props(entity):
    return getattr(entity, 'properties', None) or {}


def _attrs(entity):
    attrs = getattr(entity, 'attributes', None)
    return attrs if isinstance(attrs, dict) else {}


def _emit(entity, event):
    manager = getattr(entity, 'event_manager', None) or getattr(getattr(entity, 'session', None), 'event_manager', None)
    if manager is not None:
        manager.received_event(event)


# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------

def _map_for(entity, battle=None, battle_map=None):
    if battle_map is not None:
        return battle_map
    if battle is not None:
        try:
            found = battle.map_for(entity)
            if found is not None:
                return found
        except Exception:
            pass
    session = getattr(entity, 'session', None)
    finder = getattr(session, 'map_for_entity', None)
    if callable(finder):
        try:
            return finder(entity)
        except Exception:
            return None
    return None


def _is_night(session):
    try:
        from natural20.time_of_day import load_time_of_day_config, resolve_time_of_day
        config = load_time_of_day_config(getattr(session, 'game_properties', None) or {})
        return resolve_time_of_day(int(getattr(session, 'game_time', 0) or 0), config).is_night
    except Exception:
        return False


def in_sunlight(entity, battle=None, battle_map=None):
    if 'in_sunlight' in (getattr(entity, 'statuses', None) or []):
        return True
    current_map = _map_for(entity, battle, battle_map)
    setting = (getattr(current_map, 'properties', None) or {}).get('sunlight') if current_map else None
    if setting is True:
        return True
    if isinstance(setting, str) and setting.lower() == 'day':
        return not _is_night(getattr(entity, 'session', None))
    return False


def in_running_water(entity, battle=None, battle_map=None):
    if 'in_running_water' in (getattr(entity, 'statuses', None) or []):
        return True
    current_map = _map_for(entity, battle, battle_map)
    squares = (getattr(current_map, 'properties', None) or {}).get('running_water_squares') if current_map else None
    if not squares:
        return False
    try:
        pos = list(current_map.position_of(entity))
    except Exception:
        return False
    return any(list(square) == pos for square in squares)


def _blocked(entity, blockers, battle=None):
    blockers = blockers or []
    if 'sunlight' in blockers and in_sunlight(entity, battle):
        return 'sunlight'
    if 'running_water' in blockers and in_running_water(entity, battle):
        return 'running_water'
    return None


# --------------------------------------------------------------------------
# Legendary Resistance
# --------------------------------------------------------------------------

def legendary_resistance_max(entity):
    value = _props(entity).get('legendary_resistance')
    if value is not None and not isinstance(value, bool):
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0
    if value is True or 'legendary_resistance' in (_props(entity).get('attributes') or []):
        return DEFAULT_LEGENDARY_RESISTANCE_USES
    return 0


def legendary_resistance_remaining(entity):
    maximum = legendary_resistance_max(entity)
    used = int(_attrs(entity).get('legendary_resistance_used', 0) or 0)
    return max(0, maximum - used)


def reset_legendary_resistance(entity):
    if 'legendary_resistance_used' in _attrs(entity):
        entity.attributes['legendary_resistance_used'] = 0


DEFAULT_LEGENDARY_RESISTANCE_POLICY = {
    'concentration': 'auto',
    'concentration_min_level': 3,
    'concentration_reserve': 1,
    'concentration_per_round': 1,
}


def legendary_resistance_policy(entity):
    policy = dict(DEFAULT_LEGENDARY_RESISTANCE_POLICY)
    custom = _props(entity).get('legendary_resistance_policy')
    if isinstance(custom, dict):
        policy.update(custom)
    return policy


def _effect_spell_level(effect):
    for props in (
        getattr(effect, 'properties', None),
        getattr(getattr(getattr(effect, 'action', None), 'spell_action', None), 'properties', None),
    ):
        if isinstance(props, dict) and props.get('level') is not None:
            try:
                return int(props['level'])
            except (TypeError, ValueError):
                return 0
    return 0


def _effect_targets(effect):
    target = getattr(getattr(effect, 'action', None), 'target', None)
    members = target if isinstance(target, (list, tuple)) else [target]
    return [m for m in members if m is not None and hasattr(m, 'entity_uid')]


def _affects_enemy(entity, effect, battle):
    targets = _effect_targets(effect)
    if not targets or battle is None:
        return True
    for t in targets:
        if t is entity:
            continue
        try:
            if not battle.allies(entity, t) and not t.dead():
                return True
        except Exception:
            return True
    return False


def _concentration_uses_this_round(entity, battle) -> int:
    record = _attrs(entity).get('legendary_resistance_concentration') or {}
    if record.get('round') != getattr(battle, 'round', None):
        return 0
    return int(record.get('count', 0) or 0)


def _note_concentration_use(entity, battle):
    if battle is None:
        return
    count = _concentration_uses_this_round(entity, battle) + 1
    entity.attributes['legendary_resistance_concentration'] = {
        'round': getattr(battle, 'round', None), 'count': count}


def worth_resisting_concentration(entity, effect, battle=None):
    """Whether a concentration check on *effect* deserves a Legendary Resistance use.

    Legendary Resistance is a limited daily pool best kept for saves against
    debilitating effects; burning it to keep a minor buff up is a waste.
    """
    policy = legendary_resistance_policy(entity)
    mode = str(policy.get('concentration', 'auto')).lower()
    if mode == 'always':
        return True
    if mode == 'never':
        return False
    try:
        reserve = int(policy.get('concentration_reserve', 1) or 0)
        min_level = int(policy.get('concentration_min_level', 3) or 0)
    except (TypeError, ValueError):
        reserve, min_level = 1, 3
    if legendary_resistance_remaining(entity) <= reserve:
        return False
    # A volley (Magic Missile, Scorching Ray) forces one check per hit;
    # rescuing each of them drains the pool in a single turn.
    try:
        per_round = int(policy.get('concentration_per_round', 1))
    except (TypeError, ValueError):
        per_round = 1
    if per_round >= 0 and battle is not None and _concentration_uses_this_round(entity, battle) >= per_round:
        return False
    if effect is None or _effect_spell_level(effect) < min_level:
        return False
    return _affects_enemy(entity, effect, battle)


def try_legendary_resistance(entity, save_roll, dc, save_type, battle=None, concentration=None):
    """Turn a failed save into a success by spending a Legendary Resistance use.

    Returns the (possibly adjusted) roll. Saves against effects always use it
    when available ("can choose to succeed instead"); concentration checks
    (*concentration* = the effect at stake) follow ``legendary_resistance_policy``.
    """
    try:
        total = save_roll.result()
        dc = int(dc)
    except Exception:
        return save_roll
    if total >= dc or legendary_resistance_remaining(entity) <= 0:
        return save_roll
    if hasattr(entity, 'conscious') and not entity.conscious():
        return save_roll
    if concentration is not None and not worth_resisting_concentration(entity, concentration, battle):
        return save_roll

    from natural20.die_roll import DieRoll
    entity.attributes['legendary_resistance_used'] = int(_attrs(entity).get('legendary_resistance_used', 0) or 0) + 1
    if concentration is not None:
        _note_concentration_use(entity, battle)
    adjusted = save_roll + DieRoll.roll(f"+{dc - total}", description='legendary_resistance', entity=entity, battle=battle)
    if not hasattr(adjusted, 'metadata') or adjusted.metadata is None:
        adjusted.metadata = {}
    adjusted.metadata.update(getattr(save_roll, 'metadata', None) or {})
    adjusted.metadata['legendary_resistance'] = True
    _emit(entity, {
        'source': entity,
        'event': 'legendary_resistance',
        'save_type': save_type,
        'roll': save_roll,
        'dc': dc,
        'remaining': legendary_resistance_remaining(entity),
    })
    return adjusted


# --------------------------------------------------------------------------
# Regeneration
# --------------------------------------------------------------------------

def regeneration_config(entity):
    config = _props(entity).get('regeneration')
    if not config:
        return None
    if isinstance(config, (int, float)):
        config = {'hp': int(config)}
    if not isinstance(config, dict):
        return None
    return {
        'hp': int(config.get('hp', 0) or 0),
        'suppressed_by': [str(t).lower() for t in (config.get('suppressed_by') or [])],
        'blocked_by': [str(t).lower() for t in (config.get('blocked_by') or [])],
    }


def note_damage_for_regeneration(entity, damage_type, item=None):
    config = regeneration_config(entity)
    if not config:
        return
    types = {str(damage_type or '').lower()}
    if item:
        for key in ('weapon', 'attack_name', 'item_name'):
            if item.get(key):
                types.add(str(item[key]).lower())
    matched = types & set(config['suppressed_by'])
    if matched:
        entity.attributes['regeneration_suppressed'] = sorted(matched)[0]


def apply_regeneration(entity, battle=None):
    """Start-of-turn regeneration. Returns hit points regained."""
    config = regeneration_config(entity)
    if not config or config['hp'] <= 0:
        return 0
    suppressed = _attrs(entity).pop('regeneration_suppressed', False)
    if entity.dead() or entity.hp() < 1 or entity.hp() >= entity.max_hp():
        return 0
    if suppressed:
        reason = f"took {suppressed} damage" if isinstance(suppressed, str) else 'damage'
    else:
        reason = _blocked(entity, config['blocked_by'], battle)
    if reason:
        _emit(entity, {'source': entity, 'event': 'regeneration_blocked', 'reason': reason})
        return 0
    before = entity.hp()
    entity.heal(config['hp'])
    gained = entity.hp() - before
    if gained > 0:
        _emit(entity, {'source': entity, 'event': 'regeneration', 'value': gained})
    return gained


# --------------------------------------------------------------------------
# Misty Escape
# --------------------------------------------------------------------------

def misty_escape_config(entity):
    config = _props(entity).get('misty_escape')
    if not config:
        return None
    if config is True:
        config = {}
    if not isinstance(config, dict):
        return None
    return {
        'blocked_by': [str(t).lower() for t in (config.get('blocked_by') or ['sunlight', 'running_water'])],
        'coffin': config.get('coffin'),
        'recovery_seconds': int(config.get('recovery_seconds', 3600) or 3600),
    }


def in_mist_form(entity):
    return MIST_FORM_STATUS in (getattr(entity, 'statuses', None) or [])


def try_misty_escape(entity, battle=None, session=None):
    """Called when ``entity`` drops to 0 HP. Returns True when the trait handled
    it (turned to mist, or was destroyed because it could not transform)."""
    config = misty_escape_config(entity)
    if not config or in_mist_form(entity) or entity.dead():
        return False
    session = session or getattr(entity, 'session', None)
    blocked = _blocked(entity, config['blocked_by'], battle)
    if blocked:
        _emit(entity, {'source': entity, 'event': 'misty_escape_failed', 'reason': blocked})
        entity.make_dead(battle=battle)
        return True

    entity.attributes['hp'] = 0
    if getattr(entity, 'concentration', None) and hasattr(entity, 'drop_concentration'):
        entity.drop_concentration()
    if MIST_FORM_STATUS not in entity.statuses:
        entity.statuses.append(MIST_FORM_STATUS)
    for status in ('unconscious', 'prone', 'stable'):
        if status in entity.statuses:
            entity.statuses.remove(status)
    for grappler in list(getattr(entity, 'grapples', []) or []):
        try:
            entity.escape_grapple_from(grappler)
        except Exception:
            pass
    for target in list(getattr(entity, 'grappling', []) or []):
        try:
            target.escape_grapple_from(entity)
        except Exception:
            pass

    current_map = _map_for(entity, battle)
    if battle is not None and entity in battle.entities:
        if battle.current_turn() is entity:
            battle.consume(entity, 'action')
            battle.consume(entity, 'bonus_action')
            state = battle.entity_state_for(entity)
            if state is not None:
                state['movement'] = 0
        battle.remove(entity)
    if current_map is not None:
        try:
            current_map.remove(entity, battle=battle)
        except Exception:
            pass

    game_time = int(getattr(session, 'game_time', 0) or 0)
    entity.attributes['misty_escape'] = {
        'state': 'coffin',
        'recover_at': game_time + config['recovery_seconds'],
    }
    coffin_map = _place_in_coffin(entity, config.get('coffin'), session)
    _emit(entity, {
        'source': entity,
        'event': 'misty_escape',
        'coffin_map': getattr(coffin_map, 'name', None),
    })
    if coffin_map is not None:
        _rest_in_coffin(entity)
    return True


def _place_in_coffin(entity, coffin, session):
    if not isinstance(coffin, dict) or session is None:
        return None
    map_name = coffin.get('map')
    position = coffin.get('position')
    maps = getattr(session, 'maps', None) or {}
    coffin_map = maps.get(map_name) if isinstance(maps, dict) else None
    if coffin_map is None or not position:
        return None
    try:
        coffin_map.place(tuple(position), entity)
    except Exception:
        try:
            coffin_map.add(entity, position[0], position[1])
        except Exception:
            return None
    return coffin_map


def _rest_in_coffin(entity):
    """In the coffin the creature reverts to its true form and is paralyzed
    until it regains at least 1 hit point."""
    if MIST_FORM_STATUS in entity.statuses:
        entity.statuses.remove(MIST_FORM_STATUS)
    for status in ('paralyzed', 'incapacitated'):
        if status not in entity.statuses:
            entity.statuses.append(status)


def tick_misty_escape(entity, game_time):
    """Advance a creature recovering from Misty Escape. Returns True once it
    has regained its first hit point."""
    state = _attrs(entity).get('misty_escape')
    if not isinstance(state, dict) or entity.dead():
        return False
    if game_time < int(state.get('recover_at', 0) or 0):
        return False
    entity.attributes.pop('misty_escape', None)
    for status in (MIST_FORM_STATUS, 'paralyzed', 'incapacitated'):
        if status in entity.statuses:
            entity.statuses.remove(status)
    entity.attributes['hp'] = max(1, int(entity.attributes.get('hp', 0) or 0))
    _emit(entity, {'source': entity, 'event': 'misty_escape_recovered'})
    return True


def tick_session_misty_escapes(session):
    registry = getattr(session, 'entity_registry', None)
    entities = getattr(registry, '_uid_to_entity', None)
    if not entities:
        return
    game_time = int(getattr(session, 'game_time', 0) or 0)
    for entity in list(entities.values()):
        attrs = getattr(entity, 'attributes', None)
        if isinstance(attrs, dict) and attrs.get('misty_escape'):
            tick_misty_escape(entity, game_time)


# --------------------------------------------------------------------------
# Hit point maximum reduction (life drain)
# --------------------------------------------------------------------------

def max_hp_reduction(entity):
    try:
        return max(0, int(_attrs(entity).get('max_hp_reduction', 0) or 0))
    except (TypeError, ValueError):
        return 0


def reduce_max_hp(entity, amount, battle=None):
    """Lower ``entity``'s hit point maximum until it finishes a long rest.

    Returns True when the reduction drops the maximum to 0 and kills it.
    """
    amount = int(amount or 0)
    if amount <= 0 or entity.dead():
        return False
    entity.attributes['max_hp_reduction'] = max_hp_reduction(entity) + amount
    if entity.max_hp() <= 0:
        entity.attributes['hp'] = 0
        entity.make_dead(battle=battle)
        return True
    if entity.hp() > entity.max_hp():
        entity.attributes['hp'] = entity.max_hp()
    return False


def clear_max_hp_reduction(entity):
    _attrs(entity).pop('max_hp_reduction', None)


# --------------------------------------------------------------------------
# Charmed (source-linked condition)
# --------------------------------------------------------------------------

CHARMED_STATUS = 'charmed'
DEFAULT_CHARM_SECONDS = 86400


def _charm_table(entity):
    table = _attrs(entity).get('charmed_by')
    return table if isinstance(table, dict) else {}


def _sync_charm_status(entity):
    statuses = getattr(entity, 'statuses', None)
    if statuses is None:
        return
    if _charm_table(entity):
        if CHARMED_STATUS not in statuses:
            statuses.append(CHARMED_STATUS)
    elif CHARMED_STATUS in statuses:
        statuses.remove(CHARMED_STATUS)


def active_charmers(entity):
    """UIDs of creatures currently charming ``entity`` (expired/dead charmers pruned)."""
    table = _charm_table(entity)
    if not table:
        return []
    session = getattr(entity, 'session', None)
    now = int(getattr(session, 'game_time', 0) or 0)
    for uid, info in list(table.items()):
        until = (info or {}).get('until')
        charmer = session.entity_by_uid(uid) if session is not None and hasattr(session, 'entity_by_uid') else None
        if (until is not None and now >= int(until)) or (charmer is not None and charmer.dead()):
            table.pop(uid, None)
    if not table:
        entity.attributes.pop('charmed_by', None)
    _sync_charm_status(entity)
    return list(table.keys())


def is_charmed_by(entity, charmer):
    uid = getattr(charmer, 'entity_uid', charmer)
    return uid is not None and uid in active_charmers(entity)


def apply_charm(target, charmer, save_dc=None, duration=None, repeat_save_when_harmed=True):
    """Charm ``target`` (unless immune). Returns True when the charm took hold."""
    if target is None or charmer is None or target.dead():
        return False
    if hasattr(target, 'immune_to_condition') and target.immune_to_condition(CHARMED_STATUS):
        return False
    save_type, dc = None, None
    if save_dc:
        save_type, _, dc = str(save_dc).partition(':')
    session = getattr(target, 'session', None)
    now = int(getattr(session, 'game_time', 0) or 0)
    seconds = int(duration if duration is not None else DEFAULT_CHARM_SECONDS)
    table = dict(_charm_table(target))
    table[charmer.entity_uid] = {
        'until': now + seconds if seconds > 0 else None,
        'save_type': save_type or None,
        'dc': int(dc) if dc else None,
        'repeat_save_when_harmed': bool(repeat_save_when_harmed),
    }
    target.attributes['charmed_by'] = table
    _sync_charm_status(target)
    _emit(target, {'source': charmer, 'target': target, 'event': 'charmed'})
    return True


def end_charm(target, charmer_uid):
    table = _charm_table(target)
    if charmer_uid not in table:
        return False
    table.pop(charmer_uid, None)
    if not table:
        target.attributes.pop('charmed_by', None)
    _sync_charm_status(target)
    session = getattr(target, 'session', None)
    charmer = session.entity_by_uid(charmer_uid) if session is not None and hasattr(session, 'entity_by_uid') else None
    _emit(target, {'source': charmer or charmer_uid, 'target': target, 'event': 'charm_ended'})
    return True


def _harm_from_charmer_side(charmer, attacker, battle):
    if attacker is None or charmer is None:
        return False
    if attacker is charmer:
        return True
    if battle is None:
        return False
    try:
        return attacker in battle.entities and charmer in battle.entities and not battle.opposing(attacker, charmer)
    except Exception:
        return False


def on_harmed_while_charmed(entity, attacker, battle=None):
    """Repeat the charm save when the charmer (or its companions) harms the target."""
    if attacker is None or attacker is entity:
        return
    session = getattr(entity, 'session', None)
    for uid in active_charmers(entity):
        info = _charm_table(entity).get(uid) or {}
        if not info.get('repeat_save_when_harmed', True):
            continue
        charmer = session.entity_by_uid(uid) if session is not None and hasattr(session, 'entity_by_uid') else None
        if not _harm_from_charmer_side(charmer, attacker, battle):
            continue
        save_type, dc = info.get('save_type'), info.get('dc')
        if not save_type or not dc:
            end_charm(entity, uid)
            continue
        roll = entity.save_throw(save_type, battle, {'dc': int(dc)})
        if roll.result() >= int(dc):
            end_charm(entity, uid)


# --------------------------------------------------------------------------
# NPC attack target restrictions and riders
# --------------------------------------------------------------------------

def _target_condition(source, target, condition):
    condition = str(condition).strip().lower()
    if condition in ('willing', 'charmed_by_source'):
        return is_charmed_by(target, source)
    if condition == 'grappled_by_source':
        return source in (getattr(target, 'grapples', None) or [])
    if condition == 'grappled':
        return bool(getattr(target, 'grappled', lambda: False)())
    if condition in ('incapacitated', 'restrained', 'unconscious', 'paralyzed', 'stunned', 'prone'):
        check = getattr(target, condition, None)
        if callable(check):
            try:
                if check():
                    return True
            except Exception:
                pass
        return condition in (getattr(target, 'statuses', None) or [])
    return False


def _creature_types_of(target):
    """Lower-cased creature type descriptors (PCs are humanoids)."""
    found = []
    is_npc = getattr(target, 'npc', lambda: True)()
    is_object = getattr(target, 'object', lambda: False)()
    if not is_npc and not is_object:
        found.append('humanoid')
    props = getattr(target, 'properties', None) or {}
    for key in ('kind', 'race', 'creature_type'):
        value = props.get(key)
        if isinstance(value, (list, tuple)):
            found.extend(str(v).lower() for v in value)
        elif value:
            found.append(str(value).lower())
    return found


def attack_target_issue(source, target, npc_action):
    """Validation issue key when ``target`` can't be targeted by ``npc_action``.

    NPC action keys:

    * ``target_if: [grappled_by_source, incapacitated, restrained, willing]`` —
      any-of conditions the target must satisfy (``willing`` = charmed by the
      attacker).
    * ``target_creature_types: [humanoid]`` — allowed creature types.
    """
    if target is None or source is None:
        return None
    if getattr(target, 'object', lambda: False)():
        return None
    if is_charmed_by(source, target):
        return 'validation.attack.charmed_by_target'
    if not isinstance(npc_action, dict):
        return None
    conditions = npc_action.get('target_if')
    if conditions:
        if isinstance(conditions, str):
            conditions = [c for c in conditions.replace('|', ',').split(',') if c.strip()]
        if not any(_target_condition(source, target, c) for c in conditions):
            return 'validation.attack.target_condition'
    types = npc_action.get('target_creature_types')
    if types:
        allowed = {str(t).lower() for t in types}
        descriptors = _creature_types_of(target)
        if not any(a in d for a in allowed for d in descriptors):
            return 'validation.attack.target_creature_type'
    return None


def additional_damage_entries(npc_action):
    entries = (npc_action or {}).get('additional_damage') if isinstance(npc_action, dict) else None
    if not entries:
        return []
    if isinstance(entries, dict):
        entries = [entries]
    return [e for e in entries if isinstance(e, dict) and e.get('damage_die')]


def average_roll(die):
    try:
        from natural20.die_roll import DieRoll
        return float(DieRoll.roll(str(die)).expected())
    except Exception:
        return 0.0


def grapple_instead_config(npc_action):
    config = (npc_action or {}).get('grapple_instead') if isinstance(npc_action, dict) else None
    if not config:
        return None
    if config is True:
        config = {}
    if not isinstance(config, dict):
        return None
    return {'escape_dc': config.get('escape_dc')}
