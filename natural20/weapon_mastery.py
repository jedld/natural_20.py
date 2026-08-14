"""Weapon Mastery (SRD 5.2 / 2024) helpers.

Mastery properties on weapons are inert unless the campaign ruleset enables
weapon mastery and the attacker knows that mastery for the weapon.
"""

from __future__ import annotations

from typing import Any

# Large = 3; Push only works on Large or smaller.
_PUSH_MAX_SIZE_ID = 3

MASTERY_PROPERTIES = (
    "cleave",
    "graze",
    "nick",
    "push",
    "sap",
    "slow",
    "topple",
    "vex",
)


def _ruleset(entity) -> Any | None:
    session = getattr(entity, "session", None)
    return getattr(session, "ruleset", None) if session is not None else None


def weapon_mastery_active(entity) -> bool:
    ruleset = _ruleset(entity)
    return bool(ruleset and ruleset.weapon_mastery_enabled())


def weapon_masteries(weapon: dict | None) -> list[str]:
    if not isinstance(weapon, dict):
        return []
    raw = weapon.get("weapon_mastery") or weapon.get("mastery") or []
    if isinstance(raw, str):
        raw = [raw]
    return [str(m).lower() for m in raw if m]


def known_weapon_masteries(entity) -> set[str] | None:
    """Return known mastery names, or None meaning “all weapon masteries”."""
    props = getattr(entity, "properties", None) or {}
    known = props.get("known_weapon_masteries")
    if isinstance(known, list):
        return {str(m).lower() for m in known}
    # Class feature unlocks mastery; without an explicit known list, all apply.
    if getattr(entity, "class_feature", None) and entity.class_feature("weapon_mastery"):
        return None
    return set()


def can_use_mastery(entity, weapon: dict | None, mastery: str) -> bool:
    if not weapon_mastery_active(entity):
        return False
    mastery = mastery.lower()
    if mastery not in weapon_masteries(weapon):
        return False
    known = known_weapon_masteries(entity)
    if known is None:
        return True
    return mastery in known


def attack_ability_mod(source, weapon: dict | None) -> int:
    """Ability modifier used for the attack (STR, or DEX for finesse/ranged)."""
    if weapon is None:
        return source.str_mod()
    props = weapon.get("properties") or []
    if weapon.get("type") == "ranged_attack" or "finesse" in props:
        # Prefer higher of STR/DEX for finesse like the engine's attack_roll_mod
        if "finesse" in props:
            return max(source.str_mod(), source.dex_mod())
        return source.dex_mod()
    return source.str_mod()


def resolve_mastery_on_hit(action, battle, target, weapon, hit: bool, damage) -> list[dict]:
    """Return result items for mastery effects after hit/miss is known.

    Auto-applies non-optional riders for engine simplicity (Push/Sap/etc.).
    Cleave is skipped in v1 (needs a second attack queue).
    """
    source = action.source
    results: list[dict] = []
    if not weapon_mastery_active(source):
        return results

    if hit:
        if can_use_mastery(source, weapon, "push"):
            try:
                size_ok = target.size_identifier() <= _PUSH_MAX_SIZE_ID
            except Exception:
                size_ok = True
            if size_ok:
                results.append({
                    "type": "weapon_mastery_push",
                    "source": source,
                    "target": target,
                    "distance": 10,
                    "weapon": weapon,
                })

        if can_use_mastery(source, weapon, "sap"):
            target._sap_next_attack = True  # noqa: SLF001
            results.append({
                "type": "weapon_mastery_sap",
                "source": source,
                "target": target,
                "weapon": weapon,
            })

        if can_use_mastery(source, weapon, "vex"):
            uid = getattr(target, "entity_uid", None) or id(target)
            vex_map = getattr(source, "_vex_advantage_vs", None)
            if vex_map is None:
                source._vex_advantage_vs = {}  # noqa: SLF001
                vex_map = source._vex_advantage_vs
            vex_map[uid] = True
            results.append({
                "type": "weapon_mastery_vex",
                "source": source,
                "target": target,
                "weapon": weapon,
            })

        if can_use_mastery(source, weapon, "slow") and damage is not None:
            # Cap at −10 ft speed until start of attacker's next turn.
            target._mastery_slow_ft = 10  # noqa: SLF001
            results.append({
                "type": "weapon_mastery_slow",
                "source": source,
                "target": target,
                "speed_reduction": 10,
                "weapon": weapon,
            })

        if can_use_mastery(source, weapon, "topple"):
            ability_mod = attack_ability_mod(source, weapon)
            dc = 8 + ability_mod + source.proficiency_bonus()
            save_roll = target.save_throw("constitution", battle=battle)
            results.append({
                "type": "save_success" if save_roll.result() >= dc else "save_fail",
                "source": target,
                "save_type": "constitution",
                "roll": save_roll,
                "dc": dc,
                "reason": "weapon_mastery_topple",
            })
            if save_roll.result() < dc:
                results.append({
                    "type": "weapon_mastery_topple",
                    "source": source,
                    "target": target,
                    "weapon": weapon,
                })

    else:
        if can_use_mastery(source, weapon, "graze"):
            mod = attack_ability_mod(source, weapon)
            if mod > 0:
                results.append({
                    "type": "weapon_mastery_graze",
                    "source": source,
                    "target": target,
                    "damage": mod,
                    "damage_type": weapon.get("damage_type"),
                    "weapon": weapon,
                })

    return results


def consume_sap_disadvantage(target) -> bool:
    if getattr(target, "_sap_next_attack", False):
        target._sap_next_attack = False
        return True
    return False


def consume_vex_advantage(source, target) -> bool:
    vex_map = getattr(source, "_vex_advantage_vs", None)
    if not vex_map:
        return False
    uid = getattr(target, "entity_uid", None) or id(target)
    if vex_map.pop(uid, False):
        return True
    return False
