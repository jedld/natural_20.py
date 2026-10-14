"""YAML-driven monster summons (e.g. the SRD Vampire's *Children of the Night*).

A creature lists its summon abilities under ``summons`` in its NPC YAML::

    summons:
      - name: children_of_the_night
        label: Children of the Night
        uses_per_day: 1          # omit for unlimited
        cost: action             # action | bonus_action
        blocked_by: [sunlight]   # monster_traits blockers (sunlight, running_water)
        requires: []             # night | outdoors | indoors
        arrival: 1d4             # rounds until the creatures arrive (0 = now)
        duration: 3600           # game seconds before they leave
        dismiss: bonus_action    # cost to dismiss them all, or false
        placement_radius: 6      # squares around the summoner
        options:
          - {npc: swarm_of_bats, count: 2d4}
          - {npc: swarm_of_rats, count: 2d4}
          - {npc: wolf, count: 3d6, requires: [outdoors]}

Runtime state is kept in plain ``entity.attributes`` entries so it survives
save/load: ``summon_uses`` (name -> uses spent since the last long rest),
``pending_summons`` (creatures still on their way) and ``active_summons``
(UIDs of creatures that answered the call).  Summoned creatures carry
``properties['summoner_uid']`` / ``properties['summon_name']``.

Lifecycle: pending creatures arrive at the start of the summoner's turn once
the battle reaches their arrival round (immediately outside combat);
summons leave when ``duration`` elapses, when the summoner dies, when the
summoner takes a long rest, or when dismissed (``DismissSummonsAction``).
"""

from __future__ import annotations

from natural20.die_roll import DieRoll
from natural20.utils.monster_traits import _blocked, _emit, _is_night, _map_for

USES_ATTR = 'summon_uses'
PENDING_ATTR = 'pending_summons'
ACTIVE_ATTR = 'active_summons'


def _props(entity):
    return getattr(entity, 'properties', None) or {}


def _attrs(entity):
    attrs = getattr(entity, 'attributes', None)
    if attrs is None:
        attrs = {}
        entity.attributes = attrs
    return attrs


def summon_configs(entity):
    configs = _props(entity).get('summons') or []
    return [c for c in configs if isinstance(c, dict) and c.get('name') and c.get('options')]


def summon_config(entity, name):
    return next((c for c in summon_configs(entity) if c.get('name') == name), None)


def summon_cost(config):
    return 'bonus_action' if str((config or {}).get('cost', 'action')) == 'bonus_action' else 'action'


def dismiss_cost(config):
    value = (config or {}).get('dismiss', 'bonus_action')
    if value in (False, None, 'false', 'none'):
        return None
    return 'action' if value == 'action' else 'bonus_action'


def summon_title(config):
    return (config or {}).get('label') or str((config or {}).get('name', 'summon')).replace('_', ' ').title()


def npc_template(session, npc_type):
    from natural20.yaml_loader import load_campaign_resource_path
    try:
        if hasattr(session, '_canonical_npc_type'):
            npc_type = session._canonical_npc_type(npc_type)
        return load_campaign_resource_path(session.root_path, f"npcs/{npc_type}.yml") or {}
    except Exception:
        return {}


def npc_label(session, npc_type):
    props = npc_template(session, npc_type)
    return props.get('label') or props.get('kind') or str(npc_type).replace('_', ' ').title()


def option_label(entity, config, option):
    session = getattr(entity, 'session', None)
    name = npc_label(session, option.get('npc')) if session is not None else option.get('npc')
    return f"{summon_title(config)}: {option.get('count', 1)} {name}"


# --------------------------------------------------------------------------
# Uses
# --------------------------------------------------------------------------

def uses_remaining(entity, config):
    limit = (config or {}).get('uses_per_day')
    if limit is None:
        return None
    used = int((_attrs(entity).get(USES_ATTR) or {}).get(config['name'], 0) or 0)
    return max(0, int(limit) - used)


def _spend_use(entity, config):
    uses = _attrs(entity).setdefault(USES_ATTR, {})
    uses[config['name']] = int(uses.get(config['name'], 0) or 0) + 1


def reset_summon_uses(entity):
    if _attrs(entity).get(USES_ATTR):
        _attrs(entity)[USES_ATTR] = {}


# --------------------------------------------------------------------------
# Requirements
# --------------------------------------------------------------------------

def is_outdoors(entity, battle=None, battle_map=None):
    """Map ``outdoors: true``; maps with a ``sunlight`` setting count as
    outdoors unless ``outdoors: false`` says otherwise."""
    current_map = _map_for(entity, battle, battle_map)
    props = (getattr(current_map, 'properties', None) or {}) if current_map else {}
    if 'outdoors' in props:
        return bool(props.get('outdoors'))
    return bool(props.get('sunlight'))


def _requirement_issue(entity, requirements, battle=None):
    for requirement in requirements or []:
        if requirement == 'night' and not _is_night(getattr(entity, 'session', None)):
            return 'the sun is up'
        if requirement == 'outdoors' and not is_outdoors(entity, battle):
            return 'not outdoors'
        if requirement == 'indoors' and is_outdoors(entity, battle):
            return 'not indoors'
    return None


def summon_issue(entity, config, battle=None, option=None):
    """Why ``entity`` cannot use ``config`` (and ``option``) right now, or None."""
    if config is None:
        return 'unknown summon'
    if entity.dead() or not entity.conscious() or entity.incapacitated():
        return 'incapacitated'
    remaining = uses_remaining(entity, config)
    if remaining is not None and remaining <= 0:
        return 'no uses left'
    blocked = _blocked(entity, config.get('blocked_by') or [], battle)
    if blocked:
        return f"blocked by {blocked.replace('_', ' ')}"
    issue = _requirement_issue(entity, config.get('requires'), battle)
    if issue:
        return issue
    if option is not None:
        return _requirement_issue(entity, option.get('requires'), battle)
    return None


def available_summon_options(entity, battle=None):
    """``(config, option_index, option)`` triples usable right now."""
    found = []
    for config in summon_configs(entity):
        if summon_issue(entity, config, battle):
            continue
        for index, option in enumerate(config.get('options') or []):
            if isinstance(option, dict) and option.get('npc') and not _requirement_issue(entity, option.get('requires'), battle):
                found.append((config, index, option))
    return found


# --------------------------------------------------------------------------
# Calling and arrival
# --------------------------------------------------------------------------

def _roll(value, default=0):
    if value is None:
        return default
    try:
        return max(0, int(DieRoll.roll(str(value)).result()))
    except Exception:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return default


def _in_battle(entity, battle):
    return battle is not None and getattr(battle, 'started', False) and entity in getattr(battle, 'entities', {})


def begin_summon(entity, summon_name, option_index, battle=None, battle_map=None):
    """Spend a use and call the creatures; returns the spawned creatures
    (empty while they are still on their way)."""
    config = summon_config(entity, summon_name)
    options = (config or {}).get('options') or []
    if config is None or not (0 <= int(option_index) < len(options)):
        return []
    option = options[int(option_index)]
    _spend_use(entity, config)
    count = max(1, _roll(option.get('count', 1), 1))
    arrival = _roll(config.get('arrival'), 0)
    session = getattr(entity, 'session', None)
    label = npc_label(session, option['npc']) if session is not None else option['npc']
    entry = {
        'name': config['name'],
        'npc': option['npc'],
        'count': count,
        'arrival_rounds': arrival,
    }
    in_battle = _in_battle(entity, battle)
    _emit(entity, {
        'source': entity,
        'event': 'summon_called',
        'summon_label': summon_title(config),
        'npc_label': label,
        'count': count,
        'arrival_rounds': arrival if in_battle else 0,
    })
    if arrival > 0 and in_battle:
        entry['arrive_round'] = int(getattr(battle, 'round', 0) or 0) + arrival
        _attrs(entity).setdefault(PENDING_ATTR, []).append(entry)
        return []
    return spawn_summoned(entity, entry, battle, battle_map)


def _placement_squares(battle_map, origin, radius):
    ox, oy = origin
    width, height = battle_map.size
    candidates = []
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            if dx == 0 and dy == 0:
                continue
            x, y = ox + dx, oy + dy
            if 0 <= x < width and 0 <= y < height:
                candidates.append((max(abs(dx), abs(dy)), abs(dx) + abs(dy), x, y))
    candidates.sort()
    return [(x, y) for _, _, x, y in candidates]


def _summon_controller(summoner, battle):
    from natural20.generic_controller import GenericController
    controller = None
    try:
        controller = battle.controller_for(summoner) if battle is not None else None
    except Exception:
        controller = None
    try:
        from natural20.web.web_controller import WebController
        if isinstance(controller, WebController):
            return controller, False
    except Exception:
        pass
    return GenericController(getattr(summoner, 'session', None)), True


def spawn_summoned(entity, entry, battle=None, battle_map=None):
    session = getattr(entity, 'session', None)
    battle_map = _map_for(entity, battle, battle_map)
    if session is None or battle_map is None:
        return []
    try:
        origin = battle_map.position_of(entity)
    except Exception:
        origin = None
    if origin is None:
        return []
    config = summon_config(entity, entry.get('name')) or {}
    radius = int(config.get('placement_radius', 6) or 6)
    in_battle = _in_battle(entity, battle)
    group = battle.entities[entity].get('group') if in_battle else getattr(entity, 'group', None)
    duration = config.get('duration')
    expires_at = None
    if duration:
        expires_at = int(getattr(session, 'game_time', 0) or 0) + int(duration)

    spawned = []
    squares = iter(_placement_squares(battle_map, origin, radius))
    label = npc_label(session, entry['npc'])
    for index in range(int(entry.get('count', 1))):
        creature = session.npc(entry['npc'], {'name': f"{label} {index + 1}", 'group': group or 'b'})
        creature.group = group or creature.group
        creature.properties['summoner_uid'] = entity.entity_uid
        creature.properties['summon_name'] = entry.get('name')
        position = next(
            (sq for sq in squares if battle_map.placeable(creature, sq[0], sq[1], battle, squeeze=False)),
            None,
        )
        if position is None:
            break
        battle_map.place(position, creature, None, battle)
        if in_battle:
            controller, fresh = _summon_controller(entity, battle)
            if fresh and hasattr(controller, 'register_handlers_on'):
                try:
                    controller.register_handlers_on(creature)
                except Exception:
                    pass
            battle.add(creature, group, controller=controller, add_to_initiative=True)
        else:
            try:
                session.register_entity(creature)
            except Exception:
                pass
        _attrs(entity).setdefault(ACTIVE_ATTR, []).append({
            'uid': creature.entity_uid,
            'name': entry.get('name'),
            'expires_at': expires_at,
        })
        spawned.append(creature)

    _emit(entity, {
        'source': entity,
        'event': 'summons_arrived',
        'npc_label': label,
        'count': len(spawned),
        'summoned_uids': [c.entity_uid for c in spawned],
    })
    return spawned


def process_pending_summons(entity, battle=None, battle_map=None):
    """Spawn creatures whose arrival round has come (start of the summoner's
    turn), and send away the ones whose time is up."""
    expire_summons(entity, battle)
    pending = _attrs(entity).get(PENDING_ATTR) or []
    if not pending:
        return []
    current_round = int(getattr(battle, 'round', 0) or 0) if battle is not None else None
    arrived, waiting = [], []
    for entry in pending:
        if current_round is None or not _in_battle(entity, battle) or current_round >= int(entry.get('arrive_round', 0)):
            arrived.append(entry)
        else:
            waiting.append(entry)
    _attrs(entity)[PENDING_ATTR] = waiting
    spawned = []
    for entry in arrived:
        spawned.extend(spawn_summoned(entity, entry, battle, battle_map))
    return spawned


# --------------------------------------------------------------------------
# Leaving
# --------------------------------------------------------------------------

def _resolve(session, uid):
    if session is None or not uid:
        return None
    try:
        return session.entity_by_uid(uid)
    except Exception:
        return None


def _creature_map(creature, battle, session):
    if battle is not None:
        try:
            found = battle.map_for(creature)
            if found is not None:
                return found
        except Exception:
            pass
    for battle_map in (getattr(session, 'maps', None) or {}).values():
        try:
            if battle_map.position_of(creature) is not None:
                return battle_map
        except Exception:
            continue
    return None


def active_summons(entity, name=None):
    """Living summoned creatures still answering ``entity``."""
    session = getattr(entity, 'session', None)
    creatures = []
    for entry in _attrs(entity).get(ACTIVE_ATTR) or []:
        if name and entry.get('name') != name:
            continue
        creature = _resolve(session, entry.get('uid'))
        if creature is not None and not creature.dead():
            creatures.append(creature)
    return creatures


def has_pending_summons(entity, name=None):
    return any(not name or e.get('name') == name for e in (_attrs(entity).get(PENDING_ATTR) or []))


def dismissable_configs(entity):
    return [c for c in summon_configs(entity) if dismiss_cost(c) and active_summons(entity, c['name'])]


def dismiss_summons(entity, battle=None, name=None, reason='dismissed', include_pending=False):
    """Send summoned creatures away; returns how many left the battlefield."""
    attrs = _attrs(entity)
    keep, leaving = [], []
    for entry in attrs.get(ACTIVE_ATTR) or []:
        (leaving if not name or entry.get('name') == name else keep).append(entry)
    attrs[ACTIVE_ATTR] = keep
    if include_pending:
        attrs[PENDING_ATTR] = [e for e in attrs.get(PENDING_ATTR) or [] if name and e.get('name') != name]
    return _send_away(entity, leaving, battle, reason)


def _send_away(entity, entries, battle, reason):
    session = getattr(entity, 'session', None)
    removed = 0
    for entry in entries:
        creature = _resolve(session, entry.get('uid'))
        if creature is None or creature.dead():
            continue
        creature_map = _creature_map(creature, battle, session)
        if battle is not None and creature in getattr(battle, 'entities', {}):
            battle.remove(creature)
        if creature_map is not None:
            creature_map.remove(creature, battle=battle)
        removed += 1
    if removed:
        _emit(entity, {'source': entity, 'event': 'summons_dismissed', 'count': removed, 'reason': reason})
    return removed


def expire_summons(entity, battle=None):
    session = getattr(entity, 'session', None)
    now = int(getattr(session, 'game_time', 0) or 0)
    attrs = _attrs(entity)
    entries = attrs.get(ACTIVE_ATTR) or []
    if not entries:
        return 0
    alive = []
    for entry in entries:
        creature = _resolve(session, entry.get('uid'))
        if creature is not None and not creature.dead():
            alive.append(entry)
    expired = [e for e in alive if e.get('expires_at') is not None and now >= int(e['expires_at'])]
    attrs[ACTIVE_ATTR] = [e for e in alive if e not in expired]
    return _send_away(entity, expired, battle, 'expired') if expired else 0


def on_summoner_death(entity, battle=None):
    if not (_attrs(entity).get(ACTIVE_ATTR) or _attrs(entity).get(PENDING_ATTR)):
        return 0
    return dismiss_summons(entity, battle, reason='summoner died', include_pending=True)


def option_ai_value(entity, config, option, enemy_count=1):
    """Heuristic worth of calling ``option``: expected extra damage the
    creatures add over a couple of rounds, discounted by their arrival time."""
    from natural20.utils.monster_traits import average_roll
    if enemy_count <= 0 or has_pending_summons(entity, config['name']) or active_summons(entity, config['name']):
        return 0.0
    props = npc_template(getattr(entity, 'session', None), option.get('npc'))
    attacks = [a for a in props.get('actions') or [] if a.get('type') in ('melee_attack', 'ranged_attack')]
    per_creature = max((average_roll(a.get('damage_die', a.get('damage', 0))) for a in attacks), default=1.0)
    count = average_roll(option.get('count', 1)) or 1.0
    arrival = average_roll(config.get('arrival') or 0)
    return float(count * per_creature * 0.6 * 2 / (1 + 0.25 * arrival))


def summoner_of(creature):
    uid = _props(creature).get('summoner_uid')
    return _resolve(getattr(creature, 'session', None), uid)


def vanish_on_death(creature, battle=None):
    """NPC YAML ``vanish_on_death: true`` (summoned spirits): at 0 HP the
    creature disappears instead of leaving a body, and a summoner's spell
    that keeps it (e.g. Summon Fiend) ends."""
    if not _props(creature).get('vanish_on_death'):
        return False
    session = getattr(creature, 'session', None)
    summoner = summoner_of(creature)
    if summoner is not None:
        for entry in list(getattr(summoner, 'casted_effects', None) or []):
            effect = entry.get('effect')
            if getattr(effect, 'creature_uid', None) == creature.entity_uid:
                summoner.dismiss_effect(effect)
                return True
    creature_map = _creature_map(creature, battle, session)
    if battle is not None and creature in getattr(battle, 'entities', {}):
        battle.remove(creature)
    if creature_map is not None:
        creature_map.remove(creature, battle=battle)
    _emit(creature, {'source': summoner or creature, 'event': 'summons_dismissed', 'count': 1,
                     'reason': 'destroyed'})
    return True
