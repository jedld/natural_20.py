"""Creatures temporarily removed from the plane (Banishment, Blink).

An off-plane creature keeps its square on the map but can't be targeted
(``Entity.allow_targeting``), isn't caught by area effects
(``Map.thing_at`` honours ``allow_targeting``) and is drawn with its status icon. The state lives in
``attributes['off_plane']`` (``{'reason': 'banished', 'source_uid': ...}``)
so it survives a save.
"""

from __future__ import annotations

KEY = 'off_plane'


def off_plane(entity) -> bool:
    attrs = getattr(entity, 'attributes', None)
    return isinstance(attrs, dict) and bool(attrs.get(KEY))


def send_off_plane(entity, reason, source=None, incapacitated=False):
    if entity is None:
        return False
    entity.attributes[KEY] = {
        'reason': str(reason),
        'source_uid': getattr(source, 'entity_uid', None),
        'incapacitated': bool(incapacitated),
    }
    statuses = getattr(entity, 'statuses', None)
    if isinstance(statuses, list):
        if reason not in statuses:
            statuses.append(reason)
        if incapacitated and 'incapacitated' not in statuses:
            statuses.append('incapacitated')
    _emit(entity, source, 'off_plane', reason)
    return True


def return_to_plane(entity, battle=None):
    info = (getattr(entity, 'attributes', None) or {}).pop(KEY, None)
    if not info:
        return False
    statuses = getattr(entity, 'statuses', None)
    if isinstance(statuses, list):
        reason = info.get('reason')
        if reason in statuses:
            statuses.remove(reason)
        if info.get('incapacitated') and 'incapacitated' in statuses:
            statuses.remove('incapacitated')
    _make_room(entity, battle)
    _emit(entity, None, 'returned_to_plane', info.get('reason'))
    return True


def _make_room(entity, battle=None):
    """Move the creature to the nearest open square if its own was taken."""
    session = getattr(entity, 'session', None)
    battle_map = None
    try:
        battle_map = battle.map_for(entity) if battle is not None else session.map_for_entity(entity)
    except Exception:
        battle_map = None
    if battle_map is None:
        return
    try:
        x, y = battle_map.position_of(entity)
    except Exception:
        return
    others = [e for e in battle_map.entities_at(x, y) if e is not entity]
    if not others:
        return
    for radius in range(1, 4):
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                nx, ny = x + dx, y + dy
                try:
                    if battle_map.placeable(entity, nx, ny, battle):
                        battle_map.move_to(entity, nx, ny, battle)
                        return
                except Exception:
                    continue


def _emit(entity, source, event, reason):
    session = getattr(entity, 'session', None)
    if session is None:
        return
    session.event_manager.received_event({
        'event': event, 'source': source or entity, 'target': entity, 'reason': reason,
    })
