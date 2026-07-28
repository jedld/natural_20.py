"""NPC LLM notification generation for witnessed pickpocket attempts.

When NPCs witness a PC attempting to pickpocket another creature, this module
generates system notes that are injected into the NPC's LLM conversation
context so they can react in character.

Pickpocket notifications differ from container theft (steal_notification.py)
because:
- The target of the pickpocket immediately knows (via passive Insight).
- Witness NPCs who saw a *failed* attempt know the target is now alert.
- Witness NPCs who saw a *successful* attempt know the target is unaware.
- The "stolen item" context is important for ownership/reaction decisions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from natural20.utils.conversation import entity_label
from natural20.utils.conversation_hostility import HOSTILITY_ESCALATION_HINT


def pickpocket_attempt_note(
    npc,
    pickpocketer,
    target,
    item_name: str,
    success: bool,
    detection_type: str = 'seen',
    *,
    can_see: bool = True,
    location_name: Optional[str] = None,
) -> str:
    """Generate a system note for an NPC that witnessed a pickpocket attempt.

    This note is injected into the NPC's LLM conversation context via
    ``ConversationService.inject_npc_llm_system_note``.

    Args:
        npc: The NPC that witnessed the attempt.
        pickpocketer: The PC/NPC who attempted the pickpocket.
        target: The entity being pickpocketed.
        item_name: The name of the item being stolen.
        success: Whether the pickpocket attempt succeeded.
        detection_type: One of 'seen', 'passive_perception', 'heard'.
        can_see: Whether the NPC could see the attempt.
        location_name: Optional name of the general location.

    Returns:
        A string note to inject into the NPC's LLM context.
    """
    npc_name = entity_label(npc)
    picker_name = entity_label(pickpocketer)
    target_name = entity_label(target)

    # Build the observation description based on detection type and outcome
    if can_see and detection_type in ('seen', 'passive_perception'):
        if success:
            observation = (
                f"You saw {picker_name} successfully pickpocket '{item_name}' "
                f"from {target_name}. {target_name} appears completely unaware."
            )
        else:
            observation = (
                f"You witnessed {picker_name} attempt to pickpocket {target_name} "
                f"for '{item_name}', but the attempt failed — {target_name} noticed!"
            )
    elif detection_type == 'heard':
        if success:
            observation = (
                f"You heard a commotion and suspect a pickpocket attempt may have "
                f"occurred involving {picker_name} and {target_name}, but you "
                f"could not see what happened."
            )
        else:
            observation = (
                f"You heard raised voices and a commotion, suggesting a failed "
                f"pickpocket attempt involving {picker_name} and {target_name}."
            )
    else:
        observation = (
            f"You noticed {picker_name} acting suspiciously near {target_name}."
        )

    # Build the reaction prompt based on context
    reaction_prompt = (
        "Decide whether to react at all — you may stay silent, look away, or only "
        "respond later if that fits your character (e.g. you are allied with the "
        "pickpocketer, you do not care, or you want more information). "
        "If you do react out loud, you may speak immediately; you do not need to "
        "wait for them to speak first. Options if you react include:\n"
        "- If you know the target: alert them discreetly, confront the thief, "
        "or call for help.\n"
        "- If you don't know the target well: note the thief's appearance, "
        "warn others nearby, or offer to help.\n"
        "- If the situation seems dangerous: quietly observe and perhaps "
        "warn the target later.\n"
        "Keep any spoken reaction to one or two short sentences. "
        f"{HOSTILITY_ESCALATION_HINT}"
    )

    note = (
        f"PICKPOCKET ATTEMPT: {observation} "
        f"{reaction_prompt}"
    )

    return note


def pickpocket_victim_caught_note(
    victim,
    pickpocketer,
    item_name: str,
) -> str:
    """Generate a system note for the NPC victim who caught a pickpocket attempt."""
    picker_name = entity_label(pickpocketer)
    observation = (
        f"{picker_name} just tried to pickpocket '{item_name}' from you "
        f"and your passive Insight caught them in the act."
    )
    reaction_prompt = (
        "Decide whether to react at all — you may stay silent, look away, or only "
        "respond later if that fits your character. "
        "If you do react out loud, you may speak immediately; you do not need to "
        "wait for them to speak first. "
        "You know they tried to steal from you. Confront them, call for help, "
        "or react as your character would — or choose not to react. "
        "Keep any spoken reaction to one or two short sentences. "
        f"{HOSTILITY_ESCALATION_HINT}"
    )
    return f"PICKPOCKET CAUGHT: {observation} {reaction_prompt}"


def pc_pickpocket_detected_message(
    pc,
    target,
    item_name: str,
    witnesses: List[str],
    *,
    success: bool,
) -> str:
    """Player-facing warning when a pickpocket attempt is noticed."""
    del pc
    target_name = entity_label(target) if target else 'the target'
    witness_text = ', '.join(witnesses) if witnesses else None

    if not success:
        message = (
            f"Pickpocket failed: {target_name} noticed your attempt to steal "
            f"'{item_name}'."
        )
        if witness_text:
            message += f" {witness_text} also witnessed the attempt."
        return message

    if witness_text:
        return (
            f"Pickpocket succeeded, but you may have been seen by {witness_text} "
            f"while taking '{item_name}' from {target_name}."
        )
    return ''


def pickpocket_success_note(
    npc,
    pickpocketer,
    target,
    item_name: str,
    *,
    can_see: bool = True,
) -> str:
    """Generate a note for NPCs who saw a *successful* pickpocket (target unaware).

    This is for NPCs who witnessed the sleight of hand but the target
    didn't notice — they may want to react secretly or alert others.
    """
    npc_name = entity_label(npc)
    picker_name = entity_label(pickpocketer)
    target_name = entity_label(target)

    if can_see:
        note = (
            f"[OBSERVATION] {npc_name} saw {picker_name} skillfully lift "
            f"'{item_name}' from {target_name} without the target noticing. "
            f"{target_name} is completely unaware of the theft."
        )
    else:
        note = (
            f"[SOUND] {npc_name} heard a sudden silence after a commotion "
            f"suggesting {picker_name} may have successfully pickpocketed "
            f"'{item_name}' from {target_name}."
        )

    note += (
        " Consider whether to alert the target discreetly or warn others."
    )

    return note


def pickpocket_failed_note(
    npc,
    pickpocketer,
    target,
    item_name: str,
    *,
    can_see: bool = True,
) -> str:
    """Generate a note for NPCs who saw a *failed* pickpocket attempt.

    The target is now aware and alert — NPCs should react to the
    escalated situation.
    """
    npc_name = entity_label(npc)
    picker_name = entity_label(pickpocketer)
    target_name = entity_label(target)

    if can_see:
        note = (
            f"[ALERT] {npc_name} witnessed {picker_name} fail to pickpocket "
            f"'{item_name}' from {target_name}. {target_name} noticed the "
            f"attempt and is now aware."
        )
    else:
        note = (
            f"[SOUND] {npc_name} heard raised voices and a commotion, "
            f"suggesting {picker_name}'s pickpocket attempt on {target_name} "
            f"was detected."
        )

    note += (
        " React to the now-tense situation. Consider intervening or alerting others."
    )

    return note


def multiple_pickpocket_attempts_note(
    npc,
    pickpocketer,
    target,
    item_name: str,
    success: bool,
    *,
    previous_attempts: int = 0,
    can_see: bool = True,
) -> str:
    """Generate a note for repeated pickpocket attempts by the same PC.

    When a PC has attempted pickpocket multiple times, NPCs who witnessed
    earlier attempts should have heightened awareness and stronger reactions.

    Returns:
        A string note to inject into the NPC's LLM context.
    """
    picker_name = entity_label(pickpocketer)
    target_name = entity_label(target)

    if previous_attempts > 0:
        context = (
            f"This is another pickpocket attempt by {picker_name} — you've now "
            f"witnessed {previous_attempts + 1} suspicious act(s) from this person. "
        )
    else:
        context = ""

    if success:
        observation = (
            f"{context}You saw {picker_name} successfully lift '{item_name}' "
            f"from {target_name} again without detection."
        )
    else:
        observation = (
            f"{context}You witnessed {picker_name} fail to pickpocket "
            f"'{item_name}' from {target_name} — the target noticed again."
        )

    note = (
        f"REPEATED PICKPOCKET: {observation} "
        "Given the repeated behavior, you should take more decisive action. "
        "Consider alerting guards, confronting the thief, or warning the target."
    )

    return note
