"""Frightened (source-linked condition).

A creature can be frightened of several sources at once. Each source is
tracked in ``entity.attributes['frightened_by']`` keyed by the source's UID::

    {'until': <game_time or None>, 'save_type': 'wisdom', 'dc': 15,
     'ends_on_damage': True, 'action_limit': True, 'label': 'abjure_foes'}

Rules implemented (SRD):

* Disadvantage on attack rolls and ability checks while a source of its fear
  is within line of sight.
* ``ends_on_damage``: the condition ends when the creature takes damage
  (e.g. Abjure Foes, Turn the Unholy style effects).
* ``action_limit``: on each of its turns the creature can move, take an
  action, or take a bonus action, but only one of the three
  (``enforce_action_limit`` is called from ``Battle.commit``).

The ``frightened`` status is kept in sync with the table so the VTT and
controllers see it. Immunity (``immune_to_condition('frightened')``, which
includes Aura of Courage) prevents the condition.
"""

from __future__ import annotations

FRIGHTENED_STATUS = 'frightened'
DEFAULT_FEAR_SECONDS = 60


def _table(entity):
    attrs = getattr(entity, 'attributes', None)
    if not isinstance(attrs, dict):
        return {}
    table = attrs.get('frightened_by')
    return table if isinstance(table, dict) else {}


def _sync_status(entity):
    statuses = getattr(entity, 'statuses', None)
    if statuses is None:
        return
    if _table(entity):
        if FRIGHTENED_STATUS not in statuses:
            statuses.append(FRIGHTENED_STATUS)
    elif FRIGHTENED_STATUS in statuses:
        statuses.remove(FRIGHTENED_STATUS)


def _emit(entity, event):
    session = getattr(entity, 'session', None)
    manager = getattr(session, 'event_manager', None)
    if manager is not None:
        manager.received_event(event)


def _entity_by_uid(entity, uid):
    session = getattr(entity, 'session', None)
    if session is None or not hasattr(session, 'entity_by_uid'):
        return None
    return session.entity_by_uid(uid)


def apply_fear(target, source, save_dc=None, duration=None, ends_on_damage=False,
               action_limit=False, label=None, must_flee=False):
    """Frighten ``target`` of ``source``. Returns True when the condition took hold.

    ``must_flee``: the creature must Dash away from ``source`` on its turns
    (Fear spell); AI controllers honour it through ``flee_source``."""
    if target is None or source is None or target.dead():
        return False
    if hasattr(target, 'immune_to_condition') and target.immune_to_condition(FRIGHTENED_STATUS):
        return False
    save_type, dc = None, None
    if save_dc:
        save_type, _, dc = str(save_dc).partition(':')
    session = getattr(target, 'session', None)
    now = int(getattr(session, 'game_time', 0) or 0)
    seconds = int(duration if duration is not None else DEFAULT_FEAR_SECONDS)
    table = dict(_table(target))
    table[source.entity_uid] = {
        'until': now + seconds if seconds > 0 else None,
        'save_type': save_type or None,
        'dc': int(dc) if dc else None,
        'ends_on_damage': bool(ends_on_damage),
        'action_limit': bool(action_limit),
        'must_flee': bool(must_flee),
        'label': label,
    }
    target.attributes['frightened_by'] = table
    _sync_status(target)
    _emit(target, {'source': source, 'target': target, 'event': 'frightened', 'label': label})
    return True


def end_fear(target, source_uid):
    table = _table(target)
    if source_uid not in table:
        return False
    table.pop(source_uid, None)
    if not table:
        target.attributes.pop('frightened_by', None)
    _sync_status(target)
    source = _entity_by_uid(target, source_uid)
    _emit(target, {'source': source or source_uid, 'target': target, 'event': 'fear_ended'})
    return True


def active_fear_sources(entity):
    """UIDs of creatures ``entity`` is currently frightened of (expired/dead pruned)."""
    table = _table(entity)
    if not table:
        _sync_status(entity)
        return []
    session = getattr(entity, 'session', None)
    now = int(getattr(session, 'game_time', 0) or 0)
    for uid, info in list(table.items()):
        until = (info or {}).get('until')
        source = _entity_by_uid(entity, uid)
        if (until is not None and now >= int(until)) or (source is not None and source.dead()):
            table.pop(uid, None)
    if not table:
        entity.attributes.pop('frightened_by', None)
    _sync_status(entity)
    return list(table.keys())


def is_frightened_of(entity, source):
    uid = getattr(source, 'entity_uid', source)
    return uid is not None and uid in active_fear_sources(entity)


def fear_source_in_sight(entity, battle=None):
    """True when a source of ``entity``'s fear is within its line of sight.

    Fear with no resolvable source (or no map to check) counts as in sight so
    the disadvantage still applies.
    """
    uids = active_fear_sources(entity)
    if not uids:
        return False
    battle_map = None
    if battle is not None and hasattr(battle, 'map_for'):
        battle_map = battle.map_for(entity)
    if battle_map is None:
        session = getattr(entity, 'session', None)
        if session is not None and hasattr(session, 'map_for'):
            try:
                battle_map = session.map_for(entity)
            except Exception:
                battle_map = None
    for uid in uids:
        source = _entity_by_uid(entity, uid)
        if source is None or battle_map is None:
            return True
        try:
            if battle_map.can_see(entity, source):
                return True
        except Exception:
            return True
    return False


def fear_disadvantage(entity, battle=None):
    return ['frightened'] if fear_source_in_sight(entity, battle) else []


def on_damaged_while_frightened(entity):
    for uid in list(active_fear_sources(entity)):
        if (_table(entity).get(uid) or {}).get('ends_on_damage'):
            end_fear(entity, uid)


def has_action_limit(entity):
    return any((_table(entity).get(uid) or {}).get('action_limit')
               for uid in active_fear_sources(entity))


def flee_source(entity):
    """The creature ``entity`` must flee from this turn (``must_flee`` fear), or None."""
    for uid in active_fear_sources(entity):
        if (_table(entity).get(uid) or {}).get('must_flee'):
            source = _entity_by_uid(entity, uid)
            if source is not None and not source.dead():
                return source
    return None


def flee_choice(entity, battle, actions):
    """Pick the controller step for a creature that must flee ``flee_source``.

    Dash first while the action is unspent, then the move that ends farthest
    from the source (only if it gains distance). ``None`` means nothing useful
    is left (nowhere to run)."""
    source = flee_source(entity)
    if source is None or battle is None:
        return None
    battle_map = battle.map_for(entity)
    if battle_map is None or source not in getattr(battle_map, 'entities', {}):
        return None
    state = battle.entity_state_for(entity) or {}
    for action in actions:
        if getattr(action, 'action_type', None) == 'dash' and state.get('action', 0) > 0:
            return action
    sx, sy = battle_map.position_of(source)
    here = battle_map.position_of(entity)

    def distance(pos):
        return max(abs(int(pos[0]) - sx), abs(int(pos[1]) - sy))

    best, best_distance = None, distance(here)
    for action in actions:
        path = getattr(action, 'move_path', None)
        if getattr(action, 'action_type', None) != 'move' or not path or len(path) < 2:
            continue
        d = distance(path[-1])
        if d > best_distance:
            best, best_distance = action, d
    return best


_TURN_RESOURCES = ('action', 'bonus_action', 'movement')


def snapshot_turn_resources(battle, entity):
    if battle is None or entity is None or not getattr(entity, 'attributes', {}).get('frightened_by'):
        return None
    state = battle.entity_state_for(entity)
    if not state:
        return None
    return {key: state.get(key, 0) for key in _TURN_RESOURCES}


def enforce_action_limit(battle, entity, before):
    """Spending one of move/action/bonus action forfeits the other two."""
    if before is None or not has_action_limit(entity):
        return
    state = battle.entity_state_for(entity)
    if not state:
        return
    spent = [key for key in _TURN_RESOURCES if (state.get(key, 0) or 0) < (before.get(key, 0) or 0)]
    if not spent:
        return
    for key in _TURN_RESOURCES:
        if key != spent[0]:
            state[key] = 0
