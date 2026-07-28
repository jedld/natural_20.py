"""Pickpocket detection utilities for NPC awareness of pickpocket attempts.

When a PC or NPC attempts to pickpocket another creature, this module
checks whether nearby NPCs can see or hear the attempt and determines
if they notice based on passive Perception vs the pickpocket's Sleight
of Hand check total.

Unlike container theft (steal_detection.py), pickpocketing involves
direct interaction with a creature target — the target is resolved in
PickpocketAction (Sleight of Hand vs passive Insight in this engine).
Nearby NPC witnesses use passive Perception vs the same Sleight of Hand
total (PHB: observers notice manual trickery they can perceive).

Detection logic:
- Vision: If the NPC can see the pickpocketer, passive Perception must
  meet or exceed the pickpocketer's Sleight of Hand check total.
- Hearing: If the NPC cannot see but is within hearing range (30 ft),
  the same Sleight of Hand total applies (with adjacency bonuses).
- Proximity: NPCs adjacent to both the pickpocketer and target get +2
  to their effective passive Perception for subtle movement.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from natural20.utils.conversation import (
    entity_label,
    passive_perception_for,
    conversation_reachability,
)


def _entity_uid(entity) -> Optional[str]:
    """Extract a string UID from an entity, returning None if unavailable."""
    if entity is None:
        return None
    uid = getattr(entity, 'entity_uid', None)
    return str(uid) if uid else None


def _resolve_sleight_of_hand_dc(sleight_of_hand_total=None) -> Optional[int]:
    """Return the witness notice DC from the pickpocket Sleight of Hand total."""
    if sleight_of_hand_total is None:
        return None
    try:
        return int(sleight_of_hand_total)
    except (TypeError, ValueError):
        return None


def sleight_of_hand_total_from_roll(roll) -> Optional[int]:
    """Extract an integer Sleight of Hand total from a DieRoll-like object."""
    if roll is None:
        return None
    try:
        if hasattr(roll, 'result') and callable(roll.result):
            return int(roll.result())
        return int(roll)
    except (TypeError, ValueError):
        return None


def _check_npc_detection(
    npc,
    pickpocketer,
    target,
    battle_map,
    battle=None,
    *,
    success: bool = False,
    sleight_of_hand_total=None,
) -> Dict[str, Any]:
    """Evaluate whether a single NPC notices a pickpocket attempt.

    Witnesses compare passive Perception to the pickpocketer's Sleight of
    Hand check total (not Stealth — hiding is handled by line-of-sight).

    Args:
        npc: The witness NPC to evaluate.
        pickpocketer: The entity attempting the pickpocket.
        target: The entity being pickpocketed.
        battle_map: The battle map for vision checks.
        battle: Optional battle context (unused; kept for API compatibility).
        success: Whether the pickpocket attempt succeeded.
        sleight_of_hand_total: Integer total from the pickpocket SoH roll.

    Returns a dict with:
        - noticed: bool
        - reason: str
        - detection_type: 'passive_perception' | 'heard' | 'unaware' | ...
        - npc_passive_perception: int
        - pickpocketer_sleight_of_hand_dc: int | None
        - can_see_pickpocketer: bool
        - can_hear_pickpocketer: bool
        - is_adjacent_to_both: bool
    """
    soh_dc = _resolve_sleight_of_hand_dc(sleight_of_hand_total)
    result = {
        'noticed': False,
        'reason': '',
        'detection_type': '',
        'npc_passive_perception': passive_perception_for(npc),
        'pickpocketer_sleight_of_hand_dc': soh_dc,
        # Back-compat for callers/tests that still read the old key.
        'pickpocketer_stealth_dc': soh_dc,
        'can_see_pickpocketer': False,
        'can_hear_pickpocketer': False,
        'is_adjacent_to_both': False,
    }

    if npc is None or pickpocketer is None or target is None or battle_map is None:
        result['reason'] = 'missing_entity_or_map'
        return result

    if soh_dc is None:
        result['reason'] = 'missing_sleight_of_hand_total'
        result['detection_type'] = 'unaware'
        return result

    # --- Adjacency check: NPCs near both parties are more alert ---
    npc_pos = battle_map.entity_or_object_pos(npc)
    picker_pos = battle_map.entity_or_object_pos(pickpocketer)
    target_pos = battle_map.entity_or_object_pos(target)

    is_adjacent_to_both = False
    if npc_pos and picker_pos and target_pos:
        picker_dist = abs(npc_pos[0] - picker_pos[0]) + abs(npc_pos[1] - picker_pos[1])
        target_dist = abs(npc_pos[0] - target_pos[0]) + abs(npc_pos[1] - target_pos[1])
        # Adjacent = Manhattan distance <= 2 (covers orthogonal adjacency)
        is_adjacent_to_both = (picker_dist <= 2) and (target_dist <= 2)
        result['is_adjacent_to_both'] = is_adjacent_to_both

    # --- Vision check ---
    can_see_picker = False
    try:
        can_see_picker = battle_map.can_see(npc, pickpocketer)
    except Exception:
        can_see_picker = False
    result['can_see_pickpocketer'] = can_see_picker

    if can_see_picker:
        npc_pp = result['npc_passive_perception']

        if is_adjacent_to_both:
            npc_pp += 2

        if npc_pp >= soh_dc:
            result['noticed'] = True
            result['reason'] = (
                f"{entity_label(npc)} notices {entity_label(pickpocketer)}'s "
                f"sleight of hand (passive Perception {npc_pp} vs DC {soh_dc})"
            )
            result['detection_type'] = 'passive_perception'
        else:
            result['reason'] = (
                f"{entity_label(npc)} fails to notice {entity_label(pickpocketer)}'s "
                f"sleight of hand (passive Perception {npc_pp} vs DC {soh_dc})"
            )
            result['detection_type'] = 'unaware'
        return result

    # --- Hearing check (NPC cannot see the pickpocketer) ---
    can_hear = False
    try:
        reachability = conversation_reachability(
            pickpocketer, battle_map, mode='normal', distance_ft=30
        )
        for entry in reachability:
            if _entity_uid(entry.get('entity')) == _entity_uid(npc):
                can_hear = entry.get('reachable_now', False)
                break
    except Exception:
        pass

    result['can_hear_pickpocketer'] = can_hear

    if can_hear:
        npc_pp = result['npc_passive_perception']

        if is_adjacent_to_both:
            npc_pp += 2

        if npc_pp >= soh_dc:
            result['noticed'] = True
            if success:
                result['reason'] = (
                    f"{entity_label(npc)} hears subtle movement suggesting a "
                    f"successful pickpocket (passive Perception {npc_pp} vs DC {soh_dc})"
                )
            else:
                result['reason'] = (
                    f"{entity_label(npc)} hears commotion from a failed pickpocket "
                    f"(passive Perception {npc_pp} vs DC {soh_dc})"
                )
            result['detection_type'] = 'heard'
        else:
            result['reason'] = (
                f"{entity_label(npc)} hears {entity_label(pickpocketer)} nearby "
                f"but does not notice the pickpocket (PP {npc_pp} vs DC {soh_dc})"
            )
            result['detection_type'] = 'heard_but_missed'
    else:
        result['reason'] = (
            f"{entity_label(npc)} cannot see or hear {entity_label(pickpocketer)}"
        )
        result['noticed'] = False
        result['detection_type'] = 'unaware'

    return result


def evaluate_pickpocket_detection(
    session,
    pickpocketer,
    target,
    battle=None,
    battle_map=None,
    *,
    success: bool = False,
    sleight_of_hand_total=None,
    _skip_detection: bool = False,
) -> List[Dict[str, Any]]:
    """Evaluate whether any NPCs notice a pickpocket attempt.

    Args:
        session: The current game session.
        pickpocketer: The entity performing the pickpocket.
        target: The entity being pickpocketed.
        battle: Optional battle context.
        battle_map: Optional battle map (resolved from session if None).
        success: Whether the pickpocket attempt succeeded.
        sleight_of_hand_total: Total from the pickpocket Sleight of Hand roll.
        _skip_detection: Internal flag to skip detection.

    Returns:
        List of detection results for NPCs that noticed the attempt.
    """
    if pickpocketer is None or session is None:
        return []

    if _skip_detection:
        return []

    if battle_map is None:
        try:
            battle_map = session.map_for_entity(pickpocketer)
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
        # Skip non-NPCs, the pickpocketer, the target, unconscious/dead NPCs
        if not getattr(entity, 'is_npc', lambda: False)():
            continue
        if entity is pickpocketer or entity is target:
            continue
        if not getattr(entity, 'conscious', lambda: True)():
            continue

        detection = _check_npc_detection(
            entity, pickpocketer, target, battle_map, battle=battle,
            success=success,
            sleight_of_hand_total=sleight_of_hand_total,
        )
        detection['pickpocketer'] = {
            'name': entity_label(pickpocketer),
            'uid': _entity_uid(pickpocketer),
        }
        detection['target'] = {
            'name': entity_label(target),
            'uid': _entity_uid(target),
        }
        detection['npc'] = {
            'name': entity_label(entity),
            'uid': _entity_uid(entity),
        }
        detection['npc_entity'] = entity
        if detection['noticed']:
            detections.append(detection)

    return detections


def collect_witness_npcs(
    pickpocketer,
    target,
    session,
    battle=None,
    battle_map=None,
) -> List[Dict[str, Any]]:
    """Collect information about NPCs that should be notified about a pickpocket attempt.

    Unlike evaluate_pickpocket_detection which applies passive Perception
    vs Sleight of Hand, this function identifies ALL NPCs that *could*
    perceive the attempt (they can see or hear, regardless of the roll).

    Returns a list of dicts suitable for passing to notification functions.
    """
    if pickpocketer is None or session is None:
        return []

    if battle_map is None:
        try:
            battle_map = session.map_for_entity(pickpocketer)
        except Exception:
            battle_map = None

    if battle_map is None:
        return []

    try:
        all_entities = list(battle_map.entities.keys())
    except Exception:
        all_entities = []

    witnesses: List[Dict[str, Any]] = []

    for entity in all_entities:
        if not getattr(entity, 'is_npc', lambda: False)():
            continue
        if entity is pickpocketer or entity is target:
            continue
        if not getattr(entity, 'conscious', lambda: True)():
            continue

        can_see = False
        can_hear = False
        try:
            can_see = battle_map.can_see(entity, pickpocketer)
        except Exception:
            pass

        if not can_see:
            try:
                reachability = conversation_reachability(
                    pickpocketer, battle_map, mode='normal', distance_ft=30
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
                'pickpocketer': {
                    'name': entity_label(pickpocketer),
                    'uid': _entity_uid(pickpocketer),
                },
                'target': {
                    'name': entity_label(target),
                    'uid': _entity_uid(target),
                },
            })

    return witnesses
