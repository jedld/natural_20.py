"""YAML-driven escapes: a creature teleports away once the fight turns.

NPC YAML::

    escape:
      spell: dimension_door          # a teleport spell the creature can cast
      destination:
        annotation: war_room         # squares inside this map annotation
        # pos: [x, y]                # ...or a square (nearest free square is used)
      when:
        hp_percent: 50               # own HP at or below 50%
        allies_down_percent: 50      # half its side (not counting itself) dead or down
      mode: any                      # any condition (default) or all of them
      leave_battle: true             # default: leaves the initiative order on arrival
      set_session: lieutenant_fled   # optional session flag(s)
      message: "..."                 # optional log line on arrival

On the creature's own turn every AI controller casts the spell at the
destination before anything else (``escape_action``). The spell resolves
normally (Counterspell can stop it). If the creature arrived, it leaves the
battle at the end of that turn (``process_departures`` from
``Battle.next_turn``) and stays on the map at its destination.
"""

PENDING_KEY = '_escape_pending'
ESCAPED_KEY = '_escaped'


def escape_config(entity):
    config = (getattr(entity, 'properties', None) or {}).get('escape')
    return config if isinstance(config, dict) else None


def has_escaped(entity) -> bool:
    return bool((getattr(entity, 'properties', None) or {}).get(ESCAPED_KEY))


def escape_pending(entity) -> bool:
    """Teleported (or trying to) this turn: hold position until the turn ends."""
    return bool((getattr(entity, 'properties', None) or {}).get(PENDING_KEY))


def _down(creature) -> bool:
    try:
        return creature.dead() or not creature.conscious()
    except Exception:
        return False


def escape_triggered(entity, battle, config=None) -> bool:
    config = config or escape_config(entity)
    if not config:
        return False
    when = config.get('when') or {}
    results = []
    if when.get('hp_percent') is not None:
        max_hp = entity.max_hp() or 0
        results.append(bool(max_hp) and entity.hp() * 100 <= max_hp * float(when['hp_percent']))
    if when.get('allies_down_percent') is not None:
        allies = [c for c in list(battle.entities.keys())
                  if c is not entity and not c.object() and battle.allies(c, entity)]
        if allies:
            down = sum(1 for c in allies if _down(c))
            results.append(down * 100 >= len(allies) * float(when['allies_down_percent']))
        else:
            results.append(False)
    if not results:
        return False
    return all(results) if config.get('mode') == 'all' else any(results)


def destination_squares(entity, battle_map, config):
    """Candidate arrival squares, best first."""
    destination = config.get('destination') or {}
    width, height = battle_map.size
    if destination.get('annotation'):
        annotation = battle_map.map_annotation_by_id(destination['annotation'])
        if annotation is None:
            return []
        from natural20.map_annotations import annotation_contains_point, annotation_centroid
        squares = [(x, y) for x in range(width) for y in range(height)
                   if annotation_contains_point(annotation, x, y)]
        anchor = annotation_centroid(annotation) or (squares[0] if squares else None)
    elif destination.get('pos'):
        anchor = tuple(int(v) for v in destination['pos'])
        squares = [(x, y) for x in range(max(0, anchor[0] - 2), min(width, anchor[0] + 3))
                   for y in range(max(0, anchor[1] - 2), min(height, anchor[1] + 3))]
    else:
        return []
    if anchor is None:
        return []
    return sorted(squares, key=lambda s: (max(abs(s[0] - anchor[0]), abs(s[1] - anchor[1])), s))


def escape_action(battle, entity):
    """The teleport ``SpellAction`` to cast this turn, or None."""
    if battle is None or entity is None:
        return None
    config = escape_config(entity)
    if not config or has_escaped(entity):
        return None
    try:
        if battle.current_turn() is not entity:
            return None
    except Exception:
        return None
    if not entity.conscious() or entity.incapacitated():
        return None
    if not escape_triggered(entity, battle, config):
        return None
    battle_map = battle.map_for(entity)
    if battle_map is None:
        return None
    from natural20.actions.spell_action import SpellAction
    spell = config.get('spell', 'dimension_door')
    if not SpellAction.can_cast(entity, battle, spell):
        return None
    try:
        step = SpellAction(entity.session, entity, 'spell').build_map()['next']([spell, 0])
    except Exception:
        return None
    params = (step or {}).get('param') or []
    if not params or params[0].get('type') != 'select_empty_space':
        return None
    here = tuple(battle_map.position_of(entity))
    for square in destination_squares(entity, battle_map, config):
        if square == here:
            continue
        action = step['next'](list(square))
        action.validate(battle_map, list(square), battle=battle)
        if action.errors:
            continue
        entity.properties[PENDING_KEY] = True
        return action
    return None


def _arrived(entity, battle_map, config) -> bool:
    try:
        pos = tuple(battle_map.position_of(entity))
    except Exception:
        return False
    return pos in set(destination_squares(entity, battle_map, config))


def depart(battle, entity, config=None):
    """Take ``entity`` out of the initiative order; it stays on the map."""
    config = config or escape_config(entity) or {}
    entity.properties.pop(PENDING_KEY, None)
    entity.properties[ESCAPED_KEY] = True
    session = battle.session
    if config.get('leave_battle', True) and entity in battle.combat_order:
        was_current = battle.current_turn() is entity
        index = battle.current_turn_index
        battle.remove(entity)
        if was_current:
            # next_turn advances the index next; land on whoever followed us.
            battle.current_turn_index = index - 1
    if config.get('set_session'):
        from natural20.concern.generic_event_handler import normalize_session_flags
        session.update_state(normalize_session_flags(config['set_session']))
    session.event_manager.received_event({
        'event': 'escape', 'source': entity,
        'method': (session.load_spell(config.get('spell', 'dimension_door')) or {}).get('name'),
    })
    if config.get('message'):
        session.event_manager.received_event({
            'event': 'message', 'source': entity, 'message': config['message'],
        })


def process_departures(battle):
    """Called from ``Battle.next_turn`` before checking whether the battle ended."""
    for entity in list(battle.combat_order):
        properties = getattr(entity, 'properties', None) or {}
        if not properties.get(PENDING_KEY):
            continue
        properties.pop(PENDING_KEY, None)
        config = escape_config(entity)
        battle_map = battle.map_for(entity)
        if config and battle_map is not None and _arrived(entity, battle_map, config):
            depart(battle, entity, config)
