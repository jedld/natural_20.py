"""Steal detection utilities for NPC awareness of PC theft attempts.

When a PC interacts with containers/objects to move items, this module
checks whether nearby NPCs can see or hear the action and determines
if they notice based on perception vs stealth rolls.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from natural20.utils.conversation import (
    audible_entities,
    entity_label,
    passive_perception_for,
    conversation_reachability,
)
from natural20.utils.conversation_witness import witness_entity_uids


def _entity_uid(entity) -> Optional[str]:
    """Extract a string UID from an entity, returning None if unavailable."""
    if entity is None:
        return None
    uid = getattr(entity, 'entity_uid', None)
    return str(uid) if uid else None


def _resolve_container_ownership(
    container_or_object,
    session,
) -> Dict[str, Any]:
    """Resolve ownership information for a container/object.

    Tries these strategies in order:
    1. Explicit ``owner`` property on the container (entity UID string).
    2. ``owner_uid`` property (alias for ``owner``).
    3. ``owner_name`` property (human-readable fallback).
    4. ``staff_viewers`` property — the listed NPCs are treated as
       authorised staff who share ownership.
    5. ``location`` property — when set, the map name is used as the
       location hint for ownership context.

    Returns a dict with keys ``owner``, ``staff``, and ``location``,
    each an entity UID, a list of entity UIDs, or a string — or None.
    """
    if container_or_object is None:
        return {'owner': None, 'staff': [], 'location': None}

    props = getattr(container_or_object, 'properties', None)
    if props is None:
        try:
            props = getattr(container_or_object, 'properties', {})
        except Exception:
            props = {}

    owner: Any = (
        props.get('owner') or props.get('owner_uid') or props.get('owner_name')
    )
    staff = props.get('staff_viewers')
    location = props.get('location')

    # Normalise owner to a single UID or None
    if owner is not None:
        owner = str(owner)
    else:
        owner = None

    # Normalise staff to a list
    if staff is not None:
        if isinstance(staff, list):
            staff = [str(s) for s in staff]
        else:
            staff = [str(staff)]
    else:
        staff = []

    if location is not None:
        location = str(location)
    else:
        location = None

    return {'owner': owner, 'staff': staff, 'location': location}


def _is_hidden_pc(pc, battle=None) -> Tuple[bool, int]:
    """Check if a PC is currently hidden and return (is_hidden, stealth_dc).

    Returns:
        (True, stealth_roll) if the PC is hidden and the roll that determines DC.
        (False, 0) otherwise.
    """
    if pc is None:
        return False, 0

    stealth_roll = getattr(pc, 'stealth_roll', None)
    if stealth_roll is not None:
        try:
            return True, int(stealth_roll)
        except (TypeError, ValueError):
            pass

    # Fallback: compute a default DC of 10 (base) when no explicit roll is set
    stealth_check = getattr(pc, 'stealth_check', None)
    if callable(stealth_check) and battle is not None:
        try:
            result = stealth_check(battle)  # type: ignore
            if hasattr(result, 'result') and callable(result.result):
                return True, int(result.result())  # type: ignore
            if isinstance(result, (int, float)):
                return True, int(result)
            return True, int(result)  # type: ignore
        except (TypeError, ValueError, Exception):
            pass

    return False, 0


def _entity_is_stealth_proficient(entity) -> bool:
    """Check if an entity has stealth proficiency."""
    if entity is None:
        return False
    stealth_proficient = getattr(entity, 'stealth_proficient', None)
    if callable(stealth_proficient):
        try:
            return bool(stealth_proficient())
        except Exception:
            pass
    return bool(getattr(entity, 'stealth_proficient', False))


def _compute_stealth_dc(pc, battle=None) -> int:
    """Compute the Stealth DC for a PC based on their stealth roll."""
    is_hidden, stealth_roll = _is_hidden_pc(pc, battle)
    if is_hidden and stealth_roll > 0:
        return stealth_roll
    # Default: if PC is not hiding, there's no stealth DC to beat
    # (any NPC that can see them will notice naturally)
    return 0


def _check_npc_detection(
    npc,
    pc,
    battle_map,
    battle=None,
) -> Dict[str, Any]:
    """Evaluate whether a single NPC notices a PC's suspicious activity.

    Returns a dict with:
        - noticed: bool
        - reason: str
        - detection_type: 'seen' | 'heard' | 'passive_perception'
        - npc_passive_perception: int
        - pc_stealth_dc: int
        - can_see_pc: bool
        - can_hear_pc: bool
    """
    result = {
        'noticed': False,
        'reason': '',
        'detection_type': '',
        'npc_passive_perception': passive_perception_for(npc),
        'pc_stealth_dc': _compute_stealth_dc(pc, battle),
        'can_see_pc': False,
        'can_hear_pc': False,
    }

    if npc is None or pc is None or battle_map is None:
        result['reason'] = 'missing_entity_or_map'
        return result

    # --- Vision check ---
    can_see_pc = False
    try:
        can_see_pc = battle_map.can_see(npc, pc)
    except Exception:
        can_see_pc = False
    result['can_see_pc'] = can_see_pc

    if can_see_pc:
        # If the NPC can see the PC, check stealth
        stealth_dc = result['pc_stealth_dc']
        npc_pp = result['npc_passive_perception']

        if stealth_dc > 0 and npc_pp < stealth_dc:
            # PC is hidden and NPC's passive perception isn't high enough
            result['reason'] = f"{entity_label(npc)} can see {entity_label(pc)} but stealth DC {stealth_dc} > passive perception {npc_pp}"
            result['noticed'] = False
            result['detection_type'] = 'hidden'
        else:
            # Either PC isn't hiding (stealth_dc == 0) or NPC's passive perception beats it
            result['noticed'] = True
            if stealth_dc == 0:
                result['reason'] = f"{entity_label(npc)} sees {entity_label(pc)} acting suspiciously"
                result['detection_type'] = 'seen'
            else:
                result['reason'] = f"{entity_label(npc)} notices {entity_label(pc)} despite stealth (PP {npc_pp} >= DC {stealth_dc})"
                result['detection_type'] = 'passive_perception'
        return result

    # --- Hearing check (NPC cannot see the PC) ---
    # Check if the NPC can hear the PC's activities
    try:
        reachability = conversation_reachability(
            pc, battle_map, mode='normal', distance_ft=30
        )
        for entry in reachability:
            if _entity_uid(entry.get('entity')) == _entity_uid(npc):
                result['can_hear_pc'] = entry.get('reachable_now', False)
                break
    except Exception:
        pass

    if result['can_hear_pc']:
        # If NPC can hear but not see, they suspect something but can't identify
        # Lower the bar: hearing alone gives a +2 to perception (instinct)
        npc_pp = result['npc_passive_perception'] + 2
        stealth_dc = result['pc_stealth_dc']

        if stealth_dc > 0 and npc_pp < stealth_dc:
            result['reason'] = (
                f"{entity_label(npc)} hears {entity_label(pc)} nearby "
                f"but can't pinpoint the source"
            )
            result['noticed'] = False
            result['detection_type'] = 'heard_but_missed'
        else:
            result['noticed'] = True
            result['reason'] = (
                f"{entity_label(npc)} hears suspicious activity from {entity_label(pc)}"
            )
            result['detection_type'] = 'heard'
    else:
        result['reason'] = (
            f"{entity_label(npc)} cannot see or hear {entity_label(pc)}"
        )
        result['noticed'] = False
        result['detection_type'] = 'unaware'

    return result


def evaluate_steal_detection(
    session,
    pc,
    container_or_object,
    items_taken: List[Dict[str, Any]],
    battle=None,
    battle_map=None,
    *,
    _skip_detection: bool = False,
) -> List[Dict[str, Any]]:
    """Evaluate whether any NPCs notice a PC stealing from a container/object.

    This is the main entry point called from Container.transfer().

    Args:
        session: The current game session.
        pc: The Player Character performing the steal.
        container_or_object: The container/object being looted from.
        items_taken: List of dicts with keys 'item' (item name) and 'qty' (quantity).
        battle: Optional battle context.
        battle_map: Optional battle map (resolved from session if None).
        _skip_detection: Internal flag to skip detection (e.g. when a stealth
            check has already been performed and the PC is successfully hidden).

    Returns:
        List of detection results for NPCs that noticed the theft.
        Each dict has: npc, noticed, reason, detection_type, npc_passive_perception,
        pc_stealth_dc, can_see_pc, can_hear_pc, items, container, ownership
    """
    if pc is None:
        return []

    if _skip_detection:
        return []

    props = getattr(container_or_object, 'properties', None) or {}
    if props.get('steal_detection') is False:
        return []

    if battle_map is None:
        try:
            battle_map = session.map_for_entity(pc)
        except Exception:
            battle_map = None

    if battle_map is None:
        return []

    # Get all entities on the same map
    try:
        all_entities = list(battle_map.entities.keys())
    except Exception:
        all_entities = []

    detections: List[Dict[str, Any]] = []

    for entity in all_entities:
        # Skip non-NPCs, the PC themselves, unconscious/dead NPCs
        if not getattr(entity, 'is_npc', lambda: False)():
            continue
        if entity == pc:
            continue
        if not getattr(entity, 'conscious', lambda: True)():
            continue

        detection = _check_npc_detection(entity, pc, battle_map, battle=battle)
        detection['items'] = items_taken
        detection['container'] = {
            'name': entity_label(container_or_object),
            'uid': _entity_uid(container_or_object),
        }
        detection['pc'] = {
            'name': entity_label(pc),
            'uid': _entity_uid(pc),
        }
        detection['npc'] = {
            'name': entity_label(entity),
            'uid': _entity_uid(entity),
        }
        detection['npc_entity'] = entity
        detection['ownership'] = _resolve_container_ownership(
            container_or_object, session
        )
        if detection['noticed']:
            detections.append(detection)

    return detections


def collect_witness_npcs(
    pc,
    container_or_object,
    items_taken: List[Dict[str, Any]],
    session,
    battle=None,
    battle_map=None,
) -> List[Dict[str, Any]]:
    """Collect information about NPCs that should be notified about a theft.

    Unlike evaluate_steal_detection which checks stealth, this function
    identifies ALL NPCs that *should* know about the theft (they can see
    OR it's a valuable/stolen item and ownership context matters).

    Returns a list of dicts suitable for passing to notification functions.
    """
    if pc is None or session is None:
        return []

    if battle_map is None:
        try:
            battle_map = session.map_for_entity(pc)
        except Exception:
            battle_map = None

    if battle_map is None:
        return []

    try:
        all_entities = list(battle_map.entities.keys())
    except Exception:
        all_entities = []

    witnesses: List[Dict[str, Any]] = []
    ownership = _resolve_container_ownership(container_or_object, session)

    for entity in all_entities:
        if not getattr(entity, 'is_npc', lambda: False)():
            continue
        if entity == pc:
            continue
        if not getattr(entity, 'conscious', lambda: True)():
            continue

        # Check if this NPC can see the action happening
        can_see = False
        can_hear = False
        try:
            can_see = battle_map.can_see(entity, pc)
        except Exception:
            pass

        if not can_see:
            try:
                reachability = conversation_reachability(
                    pc, battle_map, mode='normal', distance_ft=30
                )
                for entry in reachability:
                    if _entity_uid(entry.get('entity')) == _entity_uid(entity):
                        can_hear = entry.get('reachable_now', False)
                        break
            except Exception:
                pass

        if can_see or can_hear:
            witnesses.append({
                'npc': entity,
                'can_see': can_see,
                'can_hear': can_hear,
                'passive_perception': passive_perception_for(entity),
                'items': items_taken,
                'container': {
                    'name': entity_label(container_or_object),
                    'uid': _entity_uid(container_or_object),
                },
                'ownership': ownership,
                'pc': {
                    'name': entity_label(pc),
                    'uid': _entity_uid(pc),
                },
            })

    return witnesses
