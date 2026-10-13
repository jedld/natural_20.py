"""Helpers for spells and abilities that target dead creatures (corpses / bones)."""

from __future__ import annotations

from typing import Iterable, List, Optional

# Creature types that are never "humanoid remains" for necromancy such as Animate Dead.
NON_HUMANOID_TYPES = frozenset({
    'aberration', 'beast', 'celestial', 'construct', 'dragon', 'elemental',
    'fey', 'fiend', 'giant', 'monstrosity', 'ooze', 'plant', 'undead',
})


def _races(entity) -> List[str]:
    race = (getattr(entity, 'properties', None) or {}).get('race') or []
    if isinstance(race, str):
        race = [race]
    return [str(r).lower() for r in race]


def is_humanoid_remains(entity) -> bool:
    races = _races(entity)
    if 'humanoid' in races:
        return True
    return bool(races) and not any(r in NON_HUMANOID_TYPES for r in races)


BODY_MOVED_ATTR = 'body_moved_to'


def is_animated_remains(entity) -> bool:
    """True while this creature's body is represented by another entity.

    Set on a corpse raised by Animate Dead (its body walks around as the
    undead) and on the destroyed undead once the corpse is restored. Such
    entities stay registered on their map without a token.
    """
    attrs = getattr(entity, 'attributes', None)
    return isinstance(attrs, dict) and bool(attrs.get(BODY_MOVED_ATTR))


def _retoken(battle_map, entity, position, battle=None):
    if entity in battle_map.entities:
        battle_map.remove(entity, battle=battle)
    battle_map.place(position, entity)


def animate_remains_into(remains, undead, battle_map, battle=None):
    """Keep ``remains`` registered (tokenless) while ``undead`` stands in for its body."""
    position = list(battle_map.position_of(remains))
    remains.attributes[BODY_MOVED_ATTR] = undead.entity_uid
    undead.properties['animated_remains_uid'] = remains.entity_uid
    _retoken(battle_map, remains, position, battle)
    return position


def restore_animated_remains(undead, battle=None):
    """When an animated undead is destroyed, its original corpse returns in its place."""
    props = getattr(undead, 'properties', None) or {}
    uid = props.get('animated_remains_uid')
    session = getattr(undead, 'session', None)
    if not uid or session is None:
        return None
    remains = session.entity_by_uid(uid)
    if remains is None or remains.attributes.get(BODY_MOVED_ATTR) != undead.entity_uid:
        return None
    maps = session.maps_for_entity(undead)
    undead_map = maps[0] if maps else (battle.map_for(undead) if battle is not None else None)
    if undead_map is None:
        return None
    position = list(undead_map.position_of(undead))

    remains_maps = session.maps_for_entity(remains) or ([undead_map] if remains in undead_map.entities else [])
    for remains_map in remains_maps:
        remains_map.remove(remains, battle=battle)
    remains.attributes.pop(BODY_MOVED_ATTR, None)
    undead.attributes[BODY_MOVED_ATTR] = remains.entity_uid
    _retoken(undead_map, undead, position, battle)
    undead_map.place(position, remains)

    try:
        session.event_manager.received_event({
            'event': 'animated_remains_restored',
            'source': undead,
            'target': remains,
        })
    except Exception:
        pass
    return remains


def seconds_since_death(entity) -> Optional[float]:
    """Game seconds since ``entity`` died, or None when the time wasn't recorded."""
    info = (getattr(entity, 'attributes', None) or {}).get('death_info') or {}
    died_at = info.get('game_time')
    session = getattr(entity, 'session', None)
    now = getattr(session, 'game_time', None)
    if not isinstance(died_at, (int, float)) or not isinstance(now, (int, float)):
        return None
    return max(0, now - died_at)


def is_corpse(entity, *, humanoid: bool = False, sizes: Optional[Iterable[str]] = None,
              max_age_seconds: Optional[int] = None) -> bool:
    if entity is None or not callable(getattr(entity, 'dead', None)) or not entity.dead():
        return False
    if is_animated_remains(entity):
        return False
    if max_age_seconds is not None:
        age = seconds_since_death(entity)
        if age is None or age > max_age_seconds:
            return False
    if humanoid and not is_humanoid_remains(entity):
        return False
    if sizes:
        try:
            if entity.size() not in set(sizes):
                return False
        except Exception:
            return False
    return True


def corpses_at(battle_map, x, y, **criteria) -> List:
    """Dead creatures occupying ``(x, y)`` that match ``is_corpse`` criteria."""
    try:
        candidates = battle_map.entities_at(x, y, require_alive=False) or []
    except Exception:
        return []
    creatures = getattr(battle_map, 'entities', {}) or {}
    return [c for c in candidates if c in creatures and is_corpse(c, **criteria)]


def corpse_criteria_from_param(param: dict) -> dict:
    """Translate ``build_map`` params (``require_humanoid``, ``corpse_sizes``,
    ``corpse_max_age_seconds``) into criteria."""
    criteria = {
        'humanoid': bool(param.get('require_humanoid')),
        'sizes': param.get('corpse_sizes'),
    }
    if param.get('corpse_max_age_seconds') is not None:
        criteria['max_age_seconds'] = int(param['corpse_max_age_seconds'])
    return criteria


def ally_corpses_only(corpses, entity, battle=None) -> List:
    """Drop corpses of creatures hostile to ``entity`` (``corpse_allies_only`` param)."""
    if battle is None:
        return list(corpses)
    return [c for c in corpses if c is entity or not battle.opposing(entity, c)]
