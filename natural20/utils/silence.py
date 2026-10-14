"""Magical silence areas.

Map objects whose properties set ``silenced: true`` (e.g. the tiles of a
Silence spell zone) mute every square they occupy. A creature with any of its
squares on a silenced tile:

* can't speak or hear (``combat_comms.speech_block_reason`` / ``can_hear``
  through ``message_spell_path.entity_in_magical_silence``),
* can't cast spells with a verbal component
  (``spell_requirements.environment_issue``).

Zones that also grant thunder immunity keep an ``immunity_override`` effect on
their occupants (see ``natural20/spell/silence_spell.py``).
"""
from __future__ import annotations


def square_silenced(battle_map, x, y) -> bool:
    if battle_map is None:
        return False
    try:
        objects = battle_map.objects_at(int(x), int(y))
    except Exception:
        return False
    for obj in objects or []:
        props = getattr(obj, 'properties', None) or {}
        if props.get('silenced'):
            return True
    return False


def _map_for(entity, battle_map=None):
    if battle_map is not None:
        return battle_map
    session = getattr(entity, 'session', None)
    if session is None or not hasattr(session, 'map_for'):
        return None
    try:
        return session.map_for(entity)
    except Exception:
        return None


def entity_in_silenced_area(entity, battle_map=None) -> bool:
    current = _map_for(entity, battle_map)
    if current is None or entity not in getattr(current, 'entities', {}):
        return False
    try:
        squares = current.entity_squares(entity) or [current.position_of(entity)]
    except Exception:
        return False
    return any(sq is not None and square_silenced(current, sq[0], sq[1]) for sq in squares)


def has_verbal_component(spell_details) -> bool:
    components = (spell_details or {}).get('components') or []
    if isinstance(components, str):
        components = [c.strip() for c in components.replace(',', ' ').split()]
    return any(str(c).lower() in ('verbal', 'v') for c in components)
