"""NPC LLM notification generation for detected thefts.

When NPCs notice a PC stealing items from containers/objects, this module
generates system notes that are injected into the NPC's LLM conversation
context so they can react in character.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from natural20.utils.conversation import entity_label
from natural20.utils.conversation_hostility import HOSTILITY_ESCALATION_HINT


def _format_item_list(items: List[Dict[str, Any]]) -> str:
    """Format a list of stolen items for the NPC LLM prompt."""
    if not items:
        return "unknown items"

    parts = []
    for entry in items:
        item_name = entry.get('item', entry.get('name', 'unknown item'))
        qty = entry.get('qty', 1)
        try:
            qty = int(qty)
        except (TypeError, ValueError):
            qty = 1
        if qty > 1:
            parts.append(f"{qty}x {item_name.replace('_', ' ')}")
        else:
            parts.append(item_name.replace('_', ' '))

    if len(parts) <= 2:
        return ' and '.join(parts)
    return ', '.join(parts[:-1]) + ', and ' + parts[-1]


def _format_container_info(container: Optional[Dict[str, Any]]) -> str:
    """Format container/source information for the NPC LLM prompt."""
    if not container:
        return 'an unspecified location'

    name = container.get('name', container.get('label', 'something'))
    return f"the {name.replace('_', ' ')}"


def pc_steal_detected_message(
    pc,
    container: Optional[Dict[str, Any]],
    items: List[Dict[str, Any]],
    witnesses: List[str],
) -> str:
    """Player-facing warning when NPCs notice a theft."""
    del pc
    item_text = _format_item_list(items)
    container_text = _format_container_info(container)
    witness_text = ', '.join(witnesses) if witnesses else 'someone nearby'
    return (
        f"Steal detected: you took {item_text} from {container_text} "
        f"and were noticed by {witness_text}."
    )


def steal_detection_note(
    npc,
    pc,
    container: Optional[Dict[str, Any]],
    items: List[Dict[str, Any]],
    detection_type: str,
    *,
    ownership_info: Optional[Dict[str, Any]] = None,
    can_see: bool = True,
    location_name: Optional[str] = None,
) -> str:
    """Generate a system note for an NPC that noticed a PC stealing.

    This note is injected into the NPC's LLM conversation context via
    ``ConversationService.inject_npc_llm_system_note``.

    Args:
        npc: The NPC that noticed the theft.
        pc: The PC who stole.
        container: Dict with 'name' and 'uid' of the container/object.
        items: List of dicts with 'item' and 'qty'.
        detection_type: One of 'seen', 'passive_perception', 'heard'.
        ownership_info: Optional dict with ownership context.
        can_see: Whether the NPC could see the PC during the theft.
        location_name: Optional name of the general location.

    Returns:
        A string note to inject into the NPC's LLM context.
    """
    npc_name = entity_label(npc)
    pc_name = entity_label(pc)

    item_text = _format_item_list(items)
    container_text = _format_container_info(container)

    # Build the observation description based on detection type
    if can_see and detection_type in ('seen', 'passive_perception'):
        observation = (
            f"You saw {pc_name} sneakily taking {item_text} from {container_text}."
        )
    elif detection_type == 'heard':
        observation = (
            f"You heard suspicious rustling and movement near {container_text}, "
            f"coming from {pc_name}'s direction."
        )
    else:
        observation = (
            f"You noticed {pc_name} acting suspiciously near {container_text}."
        )

    # Build ownership context
    ownership_text = ''
    if ownership_info:
        owner = ownership_info.get('owner', '')
        location = ownership_info.get('location', '')
        if owner:
            ownership_text = f" {owner.replace('_', ' ')}"
            if location:
                ownership_text += f" at {location.replace('_', ' ')}"
            ownership_text += "'s property."

    # Build the reaction prompt based on context
    reaction_prompt = (
        "Decide whether to react at all — you may stay silent, look away, or only "
        "respond later if that fits your character (e.g. you are in cahoots with "
        "the thief, you do not care, or you want more information). "
        "If you do react out loud, you may speak immediately; you do not need to "
        "wait for the thief to speak first. Options if you react include:\n"
        "- If you own the items or location: confront the thief directly, call for help, "
        "or try to catch them.\n"
        "- If you don't own the items but witnessed it: alert nearby people, "
        "note the thief's appearance, or offer to help.\n"
        "- If the thief seems powerful/dangerous: quietly note what happened "
        "and perhaps warn the owner later.\n"
        "Keep any spoken reaction to one or two short sentences. "
        f"{HOSTILITY_ESCALATION_HINT}"
    )

    note = (
        f"THEFT DETECTED: {observation}"
        f"This{ownership_text} "
        f"{reaction_prompt}"
    )

    return note


def attempted_steal_note(
    npc,
    pc,
    container: Optional[Dict[str, Any]],
    items: List[Dict[str, Any]],
    *,
    ownership_info: Optional[Dict[str, Any]] = None,
    location_name: Optional[str] = None,
) -> str:
    """Generate a note for NPCs who didn't directly see the theft but might suspect something.

    This is for NPCs who can hear but not see, or who were alerted by others.

    Returns:
        A string note to inject into the NPC's LLM context.
    """
    pc_name = entity_label(pc)
    item_text = _format_item_list(items)
    container_text = _format_container_info(container)

    note = (
        f"SUSPICIOUS ACTIVITY: You heard unusual noises coming from {container_text} "
        f"in the direction of {pc_name}, but couldn't see what was happening. "
        "Something seems off — perhaps a theft is in progress. "
        "Consider investigating if it's safe to do so, or alert others."
    )

    return note


def multiple_steals_note(
    npc,
    pc,
    container: Optional[Dict[str, Any]],
    items: List[Dict[str, Any]],
    *,
    ownership_info: Optional[Dict[str, Any]] = None,
    location_name: Optional[str] = None,
    previous_steals: int = 0,
) -> str:
    """Generate a note for repeated thefts by the same PC.

    When a PC has stolen multiple times, NPCs who witnessed earlier thefts
    should have heightened awareness and stronger reactions.

    Returns:
        A string note to inject into the NPC's LLM context.
    """
    pc_name = entity_label(pc)
    item_text = _format_item_list(items)

    if previous_steals > 0:
        context = (
            f"This is another theft by {pc_name} — you've now noticed "
            f"{previous_steals + 1} suspicious act(s) from this person. "
        )
    else:
        context = ""

    container_text = _format_container_info(container)

    note = (
        f"REPEATED THEFT DETECTED: {context}"
        f"You saw {pc_name} take {item_text} from {container_text}. "
        f"Given this is a repeated offense, you should take more decisive action. "
        f"Consider confronting them, alerting guards, or preparing to intercept them."
    )

    return note
