"""Attacking creatures you can't see (5e "Unseen Attackers and Targets").

Rules implemented:

* **Guessing a square** — a creature may attack a square it believes holds a
  creature it can't see. The attack roll has disadvantage (the regular
  ``target_unseen`` condition). If nothing is there the attack
  automatically misses, and the log never says whether the guess was right
  (a miss against an occupied square reads the same as an empty one).
* **Hearing** — an invisible creature that is *not hidden* gives away its
  location through noise: observers who can hear and are within hearing range
  know which square it is in (but still attack it with disadvantage).
* **Last known position** — when an unseen creature hides or moves out of
  earshot, observers keep a fading memory of where they last noticed it.

Observers' knowledge lives in the battle's per-entity state under
``unseen_memory`` (``{uid: {'pos': [x, y], 'round': n, 'map': name}}``) so
it survives save/load and is shared by every controller.

Campaign switch (``game.yml``)::

    unseen_targets:
      enabled: true         # default true; false disables blind attacks + markers
      hearing_range_ft: 60  # how far an unhidden unseen creature is heard
      memory_rounds: 2      # rounds a last-known position marker survives
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

DEFAULT_SETTINGS = {
    'enabled': True,
    'hearing_range_ft': 60,
    'memory_rounds': 2,
}

STATE_KEY = 'unseen_memory'

KIND_HEARD = 'heard'
KIND_LAST_KNOWN = 'last_known'


def settings_for(session) -> Dict[str, Any]:
    out = dict(DEFAULT_SETTINGS)
    props = getattr(session, 'game_properties', None) or {}
    raw = props.get('unseen_targets') if isinstance(props, dict) else None
    if isinstance(raw, bool):
        out['enabled'] = raw
    elif isinstance(raw, dict):
        out.update({k: v for k, v in raw.items() if k in DEFAULT_SETTINGS})
    return out


def enabled(session) -> bool:
    return bool(settings_for(session).get('enabled'))


# --------------------------------------------------------------------------- #
# Perception                                                                  #
# --------------------------------------------------------------------------- #

def _pos(battle_map, entity) -> Optional[Tuple[int, int]]:
    try:
        pos = battle_map.entity_or_object_pos(entity)
    except Exception:
        return None
    if pos is None:
        return None
    return int(pos[0]), int(pos[1])


def _is_candidate(battle, observer, creature) -> bool:
    if creature is observer or creature is None:
        return False
    if getattr(creature, 'is_admin', False):
        return False
    try:
        if creature.dead():
            return False
    except Exception:
        return False
    return battle.map_for(creature) is not None and battle.map_for(creature) is battle.map_for(observer)


def can_hear_location(battle, observer, creature, settings=None) -> bool:
    """True when *observer* can't see *creature* but hears which square it's in."""
    from natural20.utils.combat_comms import can_hear, _in_silence
    settings = settings or settings_for(battle.session)
    if not can_hear(observer) or creature.hidden() or _in_silence(creature):
        return False
    battle_map = battle.map_for(observer)
    try:
        distance_ft = battle_map.distance(observer, creature) * battle_map.feet_per_grid
    except Exception:
        return False
    return distance_ft <= int(settings.get('hearing_range_ft') or 0)


def _memory(battle, observer) -> Optional[dict]:
    state = battle.entity_state_for(observer)
    if state is None:
        return None
    memory = state.get(STATE_KEY)
    if not isinstance(memory, dict):
        memory = {}
        state[STATE_KEY] = memory
    return memory


def sensed_creatures(battle, observer) -> List[Dict[str, Any]]:
    """Unseen creatures *observer* knows (or remembers) the location of.

    Refreshes the observer's memory as a side effect. Each entry:
    ``{'uid', 'pos': (x, y), 'kind': 'heard'|'last_known', 'round'}``. Entries
    of kind ``last_known`` may be stale: the creature may have moved on.
    """
    if battle is None or observer is None or not enabled(battle.session):
        return []
    memory = _memory(battle, observer)
    if memory is None:
        return []
    settings = settings_for(battle.session)
    battle_map = battle.map_for(observer)
    current_round = int(getattr(battle, 'round', 0) or 0)

    heard = []
    for creature in list(battle.entities.keys()):
        if not _is_candidate(battle, observer, creature):
            continue
        uid = creature.entity_uid
        if battle.can_see(observer, creature):
            memory.pop(uid, None)
            continue
        if can_hear_location(battle, observer, creature, settings):
            pos = _pos(battle_map, creature)
            if pos is None:
                continue
            memory[uid] = {'pos': list(pos), 'round': current_round, 'map': battle_map.name}
            heard.append({'uid': uid, 'pos': pos, 'kind': KIND_HEARD, 'round': current_round})

    heard_uids = {h['uid'] for h in heard}
    keep_rounds = int(settings.get('memory_rounds') or 0)
    remembered = []
    for uid, entry in list(memory.items()):
        if uid in heard_uids:
            continue
        creature = battle.entity_by_uid(uid) if hasattr(battle, 'entity_by_uid') else None
        stale = (
            not isinstance(entry, dict)
            or current_round - int(entry.get('round') or 0) > keep_rounds
            or entry.get('map') != battle_map.name
            or creature is None
            or creature.dead()
        )
        if stale:
            memory.pop(uid, None)
            continue
        remembered.append({
            'uid': uid, 'pos': tuple(entry['pos']), 'kind': KIND_LAST_KNOWN,
            'round': int(entry.get('round') or 0),
        })
    return heard + remembered


def note_noise(battle, creature) -> None:
    """Record *creature*'s current square for every observer that can't see it.

    Called when an unseen creature attacks or casts: 5e attacking reveals your
    location, so even observers who could not hear it before learn where it is.
    """
    if battle is None or creature is None or not enabled(battle.session):
        return
    battle_map = battle.map_for(creature)
    pos = _pos(battle_map, creature) if battle_map is not None else None
    if pos is None:
        return
    current_round = int(getattr(battle, 'round', 0) or 0)
    from natural20.utils.combat_comms import can_hear
    for observer in list(battle.entities.keys()):
        if not _is_candidate(battle, observer, creature) or not can_hear(observer):
            continue
        if battle.can_see(observer, creature):
            continue
        memory = _memory(battle, observer)
        if memory is not None:
            memory[creature.entity_uid] = {'pos': list(pos), 'round': current_round, 'map': battle_map.name}


def _is_ally(battle, observer, uid) -> bool:
    """Allies keep each other informed: their positions aren't guesses."""
    creature = battle.entity_by_uid(uid)
    if creature is None:
        return False
    try:
        return bool(battle.allies(observer, creature))
    except Exception:
        return False


def markers_for(battle, viewers) -> Dict[Tuple[int, int], Dict[str, Any]]:
    """Square -> marker info for the map renderer (merged over *viewers*).

    Markers never name the creature: they only say a square holds something
    unseen (heard now) or held something recently (last known).
    """
    out: Dict[Tuple[int, int], Dict[str, Any]] = {}
    if battle is None:
        return out
    for viewer in viewers or []:
        if viewer is None or battle.entity_state_for(viewer) is None:
            continue
        for entry in sensed_creatures(battle, viewer):
            if any(battle.entity_by_uid(entry['uid']) is v for v in viewers):
                continue
            if _is_ally(battle, viewer, entry['uid']):
                continue
            pos = tuple(entry['pos'])
            prev = out.get(pos)
            if prev is None or (prev['kind'] != KIND_HEARD and entry['kind'] == KIND_HEARD):
                out[pos] = {'kind': entry['kind'], 'round': entry['round']}
    current_round = int(getattr(battle, 'round', 0) or 0)
    for marker in out.values():
        if marker['kind'] == KIND_HEARD:
            marker['label'] = 'Heard: something unseen is here'
        else:
            ago = max(0, current_round - marker['round'])
            when = 'this round' if ago == 0 else ('last round' if ago == 1 else f'{ago} rounds ago')
            marker['label'] = f'Last known position of an unseen creature ({when})'
    return out


# --------------------------------------------------------------------------- #
# Blind attacks                                                               #
# --------------------------------------------------------------------------- #

def has_line_of_effect(battle_map, attacker, square) -> bool:
    """A clear path to *square* ignoring light (darkness doesn't stop a swing)."""
    sx, sy = square
    for ax, ay in battle_map.entity_squares(attacker):
        if (ax, ay) == (sx, sy):
            return False
        if battle_map.line_of_sight(ax, ay, sx, sy, inclusive=False) is not None:
            return True
    return False


def square_in_bounds(battle_map, square) -> bool:
    x, y = square
    return 0 <= x < battle_map.size[0] and 0 <= y < battle_map.size[1]


def unseen_occupant(battle, attacker, square):
    """The living creature at *square* that *attacker* can't see, else None."""
    battle_map = battle.map_for(attacker)
    try:
        candidates = battle_map.entities_at(*square) or []
    except Exception:
        candidates = []
    token = battle_map.entity_at(*square)
    if token is not None and token not in candidates:
        candidates.append(token)
    for creature in candidates:
        if creature is attacker or creature is None:
            continue
        try:
            if creature.dead() or creature.object():
                continue
        except Exception:
            continue
        if not battle.can_see(attacker, creature):
            return creature
    return None


def visible_creature_at(battle, attacker, square):
    battle_map = battle.map_for(attacker)
    token = battle_map.entity_at(*square)
    if token is None or token is attacker:
        return None
    try:
        if token.dead():
            return None
    except Exception:
        return None
    return token if battle.can_see(attacker, token) else None


def makes_attack_roll(action) -> bool:
    """False for "attacks" that are really sight-based abilities (``force_hit``
    / ``no_damage`` NPC actions such as a vampire's Charm): they need a target
    the user can see, so they can't be aimed at a guessed square."""
    spec = getattr(action, 'npc_action', None)
    if not isinstance(spec, dict):
        using = getattr(action, 'using', None)
        source = getattr(action, 'source', None)
        if using and source is not None:
            spec = next((a for a in (getattr(source, 'npc_actions', None) or [])
                         if isinstance(a, dict) and str(a.get('name', '')).lower() == str(using).lower()), None)
    if isinstance(spec, dict) and (spec.get('force_hit') or spec.get('no_damage')):
        return False
    return True


def blind_attack_issue(battle, attacker, action, square) -> Optional[str]:
    """Why *attacker* can't make a blind attack with *action* at *square*.

    Returns a translation key, or None when the attack is allowed. The answer
    must not depend on whether something actually occupies the square.
    """
    if battle is None or not enabled(battle.session):
        return 'validation.unseen.disabled'
    battle_map = battle.map_for(attacker)
    if battle_map is None or not square_in_bounds(battle_map, square):
        return 'validation.unseen.out_of_bounds'
    sx, sy = square
    if battle_map.base_map[sx][sy] == '#':
        return 'validation.unseen.wall'
    if square in [tuple(s) for s in battle_map.entity_squares(attacker)]:
        return 'validation.unseen.self'
    if not makes_attack_roll(action):
        return 'validation.unseen.needs_sight'
    from natural20.weapons import compute_max_weapon_range
    try:
        attack_range = compute_max_weapon_range(battle.session, action) or 5
    except Exception:
        attack_range = 5
    if battle_map.distance_to_square(attacker, sx, sy) * battle_map.feet_per_grid > attack_range:
        return 'validation.unseen.out_of_range'
    if not has_line_of_effect(battle_map, attacker, square):
        return 'validation.unseen.no_path'
    return None


CONFIDENCE = {KIND_HEARD: 1.0, KIND_LAST_KNOWN: 0.35}


def blind_attack_variants(battle, attacker, actions) -> list:
    """Square-targeted copies of *actions* for AI controllers.

    One variant per sensed square in reach. Each carries ``blind_confidence``
    (how likely the creature is still there) for heuristic scoring.
    """
    import copy
    if battle is None or not enabled(battle.session):
        return []
    sensed = [e for e in sensed_creatures(battle, attacker) if not _is_ally(battle, attacker, e['uid'])]
    if not sensed:
        return []
    out = []
    for action in actions:
        seen_squares = set()
        for entry in sensed:
            pos = tuple(entry['pos'])
            if pos in seen_squares:
                continue
            seen_squares.add(pos)
            if blind_attack_issue(battle, attacker, action, pos) is not None:
                continue
            variant = copy.copy(action)
            variant.target = None
            variant.target_square = pos
            variant.blind_confidence = CONFIDENCE.get(entry['kind'], 0.35)
            out.append(variant)
    return out


def base_attack_actions(session, entity, battle) -> list:
    """The entity's weapon / NPC attacks with no target chosen yet."""
    from natural20.actions.attack_action import AttackAction
    if not AttackAction.can(entity, battle):
        return []
    if hasattr(entity, 'generate_npc_attack_actions'):
        return [a for a in entity.generate_npc_attack_actions(battle, auto_target=False)
                if not a.grapple_instead]
    if callable(getattr(entity, 'is_wild_shaped', None)) and entity.is_wild_shaped():
        return entity._wild_shape_attack_actions(session, battle, auto_target=False)
    if hasattr(entity, '_player_character_attack_actions'):
        return entity._player_character_attack_actions(session, battle, auto_target=False)
    return []


def blind_attack_squares(battle, attacker, action) -> List[Tuple[int, int]]:
    """Sensed squares *attacker* could currently target with *action*."""
    out = []
    for entry in sensed_creatures(battle, attacker):
        if _is_ally(battle, attacker, entry['uid']):
            continue
        pos = tuple(entry['pos'])
        if pos in out:
            continue
        if blind_attack_issue(battle, attacker, action, pos) is None:
            out.append(pos)
    return out
