"""Ally auras centred on a creature (Paladin Aura of Protection and friends).

Auras are evaluated on demand from map positions, so nothing needs to be
registered or cleaned up when creatures move, fall unconscious or are saved.

Built-in class-feature auras (SRD)::

    aura_of_protection  allies add the aura owner's CHA modifier (min +1) to saves
    aura_of_courage     allies can't be frightened
    aura_of_devotion    allies can't be charmed

Range is 10 ft, or 30 ft once the owner has the ``aura_expansion`` feature or
paladin level 18. Any creature may also declare auras in YAML::

    auras:
      - name: aura_of_warding
        range: 10                 # feet
        save_bonus: cha           # ability whose modifier (min +1) is added to saves
        condition_immunity: [charmed, frightened]
        condition_save_advantage: [frightened]   # advantage on saves vs these conditions
        creature_types: [draconian]  # only allies of these types/tags are covered
        requires: [see, hear]        # covered allies must see and/or hear the owner

An aura only works while its owner is conscious and not incapacitated, and it
always covers the owner (when the owner matches ``creature_types``). Several
save-bonus auras don't stack; the best applies.
"""

from __future__ import annotations

CLASS_FEATURE_AURAS = {
    'aura_of_protection': {'save_bonus': 'cha'},
    'aura_of_courage': {'condition_immunity': ['frightened']},
    'aura_of_devotion': {'condition_immunity': ['charmed']},
}

_ABILITY_NAMES = {
    'str': 'strength', 'dex': 'dexterity', 'con': 'constitution',
    'int': 'intelligence', 'wis': 'wisdom', 'cha': 'charisma',
}


def _class_feature(entity, feature):
    check = getattr(entity, 'class_feature', None)
    if not callable(check):
        return False
    try:
        return bool(check(feature))
    except Exception:
        return False


def _default_range(entity):
    if _class_feature(entity, 'aura_expansion'):
        return 30
    classes = (getattr(entity, 'properties', None) or {}).get('classes') or {}
    try:
        if int(classes.get('paladin', 0) or 0) >= 18:
            return 30
    except (TypeError, ValueError):
        pass
    return 10


def auras_of(entity):
    """Aura definitions ``entity`` projects (each with ``name`` and ``range``)."""
    found = []
    for feature, config in CLASS_FEATURE_AURAS.items():
        if _class_feature(entity, feature):
            found.append({'name': feature, 'range': _default_range(entity), **config})
    for raw in (getattr(entity, 'properties', None) or {}).get('auras') or []:
        if isinstance(raw, dict):
            entry = dict(raw)
            entry.setdefault('name', 'aura')
            entry.setdefault('range', 10)
            found.append(entry)
    return found


def _aura_active(owner):
    if owner is None:
        return False
    try:
        if owner.dead() or not owner.conscious():
            return False
        if callable(getattr(owner, 'incapacitated', None)) and owner.incapacitated():
            return False
    except Exception:
        return False
    return True


def _battle_for(entity, battle=None):
    if battle is not None:
        return battle
    session = getattr(entity, 'session', None)
    return getattr(session, 'current_battle', None) or getattr(session, 'battle', None)


def _map_for(entity, battle=None):
    if battle is not None and hasattr(battle, 'map_for'):
        found = battle.map_for(entity)
        if found is not None:
            return found
    session = getattr(entity, 'session', None)
    if session is not None and hasattr(session, 'map_for'):
        try:
            return session.map_for(entity)
        except Exception:
            return None
    return None


def _friendly(owner, other, battle=None):
    if owner is other:
        return True
    if battle is not None:
        try:
            if battle.entity_state_for(owner) and battle.entity_state_for(other):
                return battle.allies(owner, other)
        except Exception:
            pass
    owner_pc = not owner.npc() if hasattr(owner, 'npc') else False
    other_pc = not other.npc() if hasattr(other, 'npc') else False
    if owner_pc and other_pc:
        return True
    session = getattr(owner, 'session', None)
    try:
        from natural20.sidekick import is_sidekick
        if (owner_pc and is_sidekick(session, other)) or (other_pc and is_sidekick(session, owner)):
            return True
    except Exception:
        pass
    owner_group = (getattr(owner, 'properties', None) or {}).get('group')
    return owner_group is not None and owner_group == (getattr(other, 'properties', None) or {}).get('group')


def _type_matches(entity, aura):
    types = aura.get('creature_types')
    if not types:
        return True
    import re
    from natural20.utils.monster_traits import _creature_types_of
    words = {w for d in _creature_types_of(entity) for w in re.findall(r'[a-z]+', d)}
    return bool({str(t).lower() for t in types} & words)


def _perceives(owner, entity, aura, battle_map, battle=None):
    requires = aura.get('requires') or []
    if isinstance(requires, str):
        requires = [requires]
    statuses = getattr(entity, 'statuses', None) or []
    if 'hear' in requires and ('deafened' in statuses or 'unconscious' in statuses):
        return False
    if 'see' in requires:
        if 'blinded' in statuses:
            return False
        try:
            if battle is not None and battle.entity_state_for(entity) and battle.entity_state_for(owner):
                return bool(battle.can_see(entity, owner))
            if battle_map is not None:
                return bool(battle_map.can_see(entity, owner))
        except Exception:
            return True
    return True


def auras_affecting(entity, battle=None):
    """``(owner, aura)`` pairs whose aura currently covers ``entity``."""
    battle = _battle_for(entity, battle)
    results = []
    for aura in auras_of(entity):
        if _aura_active(entity) and _type_matches(entity, aura):
            results.append((entity, aura))
    battle_map = _map_for(entity, battle)
    if battle_map is None:
        return results
    for owner in list(getattr(battle_map, 'entities', {}) or {}):
        if owner is entity or not hasattr(owner, 'class_feature'):
            continue
        owned = auras_of(owner)
        if not owned or not _aura_active(owner) or not _friendly(owner, entity, battle):
            continue
        try:
            feet = battle_map.distance(owner, entity) * battle_map.feet_per_grid
        except Exception:
            continue
        for aura in owned:
            if feet > float(aura.get('range', 10) or 0) or not _type_matches(entity, aura):
                continue
            if not _perceives(owner, entity, aura, battle_map, battle):
                continue
            results.append((owner, aura))
    return results


def aura_save_bonus(entity, battle=None):
    """``(bonus, aura_name)`` from the best save-bonus aura covering ``entity``."""
    best, best_name = 0, None
    for owner, aura in auras_affecting(entity, battle):
        ability = aura.get('save_bonus')
        if not ability:
            continue
        try:
            mod = int(owner.ability_mod(_ABILITY_NAMES.get(ability, ability)) or 0)
        except Exception:
            mod = 0
        bonus = max(1, mod)
        if bonus > best:
            best, best_name = bonus, aura.get('name')
    return best, best_name


def aura_condition_save_advantage(entity, conditions, battle=None):
    """Name of an aura covering ``entity`` that gives advantage on saves
    against any of ``conditions``, or None."""
    wanted = {str(c).lower() for c in conditions or [] if c}
    if not wanted:
        return None
    for _owner, aura in auras_affecting(entity, battle):
        if wanted & {str(c).lower() for c in aura.get('condition_save_advantage') or []}:
            return aura.get('name') or 'aura'
    return None


def aura_condition_immunity(entity, condition, battle=None):
    """True when an aura covering ``entity`` prevents ``condition``."""
    condition = str(condition).lower()
    for _owner, aura in auras_affecting(entity, battle):
        if condition in [str(c).lower() for c in aura.get('condition_immunity') or []]:
            return True
    return False
