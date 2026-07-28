"""Helpers for NPC LLM reactions to out-of-combat hits."""

from __future__ import annotations

from typing import Any, Dict, Optional

from natural20.die_roll import Rollable
from natural20.utils.conversation import entity_label


def _damage_total(item: Dict[str, Any]) -> Optional[int]:
    damage = item.get('damage')
    if damage is None:
        return None
    if isinstance(damage, Rollable):
        total = damage.result()
    else:
        try:
            total = int(damage)
        except (TypeError, ValueError):
            return None
    sneak = item.get('sneak_attack')
    if sneak is not None:
        if isinstance(sneak, Rollable):
            total += sneak.result()
        else:
            try:
                total += int(sneak)
            except (TypeError, ValueError):
                pass
    return total


def describe_hit_kind(item: Dict[str, Any]) -> str:
    """Human-readable label for the attack or spell that landed."""
    if item.get('type') == 'spell_damage' or item.get('spell'):
        spell = item.get('spell') or {}
        name = spell.get('name') or item.get('attack_name') or 'a spell'
        return f"spell ({str(name).replace('_', ' ')})"
    attack_name = item.get('attack_name') or 'an attack'
    return f"attack ({str(attack_name).replace('_', ' ')})"


def describe_damage_type(item: Dict[str, Any]) -> str:
    damage_type = item.get('damage_type')
    if not damage_type:
        return 'unspecified'
    return str(damage_type).replace('_', ' ')


def attacker_visible_to_target(
    target,
    attacker,
    battle_map=None,
) -> bool:
    if attacker is None or target is None:
        return False
    if battle_map is None:
        return False
    can_see = getattr(battle_map, 'can_see', None)
    if not callable(can_see):
        return False
    try:
        return bool(can_see(target, attacker))
    except Exception:
        return False


def describe_attacker(
    target,
    attacker,
    *,
    battle_map=None,
    known: Optional[bool] = None,
) -> str:
    if attacker is None:
        return 'an unseen or unknown source'
    visible = known if known is not None else attacker_visible_to_target(target, attacker, battle_map)
    if not visible:
        return 'an attacker you cannot see or identify'
    return entity_label(attacker)


def out_of_combat_hit_reaction_note(
    npc,
    attacker,
    item: Dict[str, Any],
    *,
    battle_map=None,
    known_attacker: Optional[bool] = None,
) -> str:
    """System note prompting an in-character reaction to a non-combat hit."""
    kind = describe_hit_kind(item)
    damage_type = describe_damage_type(item)
    damage_total = _damage_total(item)
    attacker_desc = describe_attacker(
        npc,
        attacker,
        battle_map=battle_map,
        known=known_attacker,
    )
    damage_text = f' for {damage_total} damage' if damage_total is not None else ''
    return (
        f"You were struck outside of combat by {kind} dealing {damage_type} damage{damage_text}. "
        f"The source appears to be {attacker_desc}. "
        "React briefly in character — a shout, gasp, curse, or pained line. "
        "Keep it to one or two short sentences. Do not start combat or use action tags."
    )


def is_damage_hit_item(item: Dict[str, Any]) -> bool:
    return item.get('type') in ('damage', 'spell_damage') and item.get('target') is not None
