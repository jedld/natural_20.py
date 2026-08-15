"""Weapon Mastery (SRD 5.2 / 2024) helpers.

Mastery properties on weapons are inert unless the campaign ruleset enables
weapon mastery and the attacker knows that mastery for the weapon.
"""

from __future__ import annotations

import inspect
from typing import Any

from natural20.action import Action, AsyncReactionHandler

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

OPTIONAL_MASTERIES = frozenset({"push", "topple", "cleave", "nick"})

MASTERY_LABELS = {
    "cleave": "Cleave",
    "graze": "Graze",
    "nick": "Nick",
    "push": "Push",
    "sap": "Sap",
    "slow": "Slow",
    "topple": "Topple",
    "vex": "Vex",
}

MASTERY_BLURBS = {
    "cleave": "After a melee hit, you can make another melee attack vs a second creature within 5 ft (once per turn).",
    "graze": "On a miss, deal damage equal to the ability modifier used for the attack.",
    "nick": "When you make the extra Light-weapon attack, you can make it as part of the Attack action instead of a Bonus Action.",
    "push": "On a hit vs Large or smaller, you can push the target 10 feet away.",
    "sap": "On a hit, the target has disadvantage on its next attack roll before the start of your next turn.",
    "slow": "On a hit that deals damage, the target's Speed is reduced by 10 feet until the start of your next turn (does not stack).",
    "topple": "On a hit, you can force a Constitution save (DC 8 + attack ability + PB) or the target has the Prone condition.",
    "vex": "On a hit, you have advantage on your next attack vs that creature before the end of your next turn.",
}

# SRD 5.2 known-mastery counts by class (level threshold → count).
_KNOWN_COUNT_SCALE = {
    "fighter": ((1, 3), (4, 4), (10, 5), (16, 6)),
    "barbarian": ((1, 2), (4, 3), (10, 4), (16, 5)),
    "paladin": ((1, 2), (4, 3), (10, 4), (16, 5)),
    "ranger": ((1, 2), (4, 3), (10, 4), (16, 5)),
    "rogue": ((1, 2), (4, 3), (10, 4), (16, 5)),
}


class WeaponMasteryChoice(Action):
    """Yes/no choice used when prompting optional Push/Topple."""

    def __init__(self, session, source, mastery: str, use: bool = True):
        super().__init__(session, source, "weapon_mastery")
        self.mastery = str(mastery).lower()
        self.use = bool(use)

    def __str__(self):
        if self.mastery == "push":
            return "Push 10 feet" if self.use else "Do not push"
        if self.mastery == "topple":
            return "Topple (CON save or prone)" if self.use else "Do not topple"
        label = MASTERY_LABELS.get(self.mastery, self.mastery.title())
        return label if self.use else f"Do not use {label}"

    def label(self):
        return str(self)


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


def known_mastery_count(klass, level, class_def=None) -> int:
    """How many weapon masteries this class knows at ``level``."""
    klass_key = str(klass or "").lower()
    table = _KNOWN_COUNT_SCALE.get(klass_key)
    yaml_count = None
    if isinstance(class_def, dict) and class_def.get("weapon_mastery_known") is not None:
        try:
            yaml_count = int(class_def.get("weapon_mastery_known") or 0)
        except (TypeError, ValueError):
            yaml_count = None

    try:
        lvl = int(level or 1)
    except (TypeError, ValueError):
        lvl = 1

    if table:
        count = table[0][1]
        for threshold, n in table:
            if lvl >= threshold:
                count = n
        if yaml_count and lvl < 4:
            return yaml_count
        return count
    return yaml_count or 0


def known_weapon_masteries(entity) -> set[str] | None:
    """Return known mastery names, or None meaning “all weapon masteries”.

    An explicit list (including empty) always wins. Missing list + class
    feature (or NPC) still means all, so legacy sheets and monster attacks
    keep working until chargen writes a list.
    """
    props = getattr(entity, "properties", None) or {}
    known = props.get("known_weapon_masteries")
    if isinstance(known, list):
        return {str(m).lower() for m in known}
    if getattr(entity, "class_feature", None) and entity.class_feature("weapon_mastery"):
        return None
    npc = getattr(entity, "npc", None)
    if callable(npc) and npc():
        return None
    return set()


def can_use_mastery(entity, weapon: dict | None, mastery: str) -> bool:
    if not weapon_mastery_active(entity):
        return False
    mastery = mastery.lower()
    if mastery not in weapon_masteries(weapon):
        return False
    npc = getattr(entity, "npc", None)
    if not (callable(npc) and npc()):
        proficient = getattr(entity, "proficient_with_weapon", None)
        if callable(proficient) and weapon is not None:
            try:
                if not proficient(weapon):
                    return False
            except Exception:
                pass
    known = known_weapon_masteries(entity)
    if known is None:
        return True
    return mastery in known


def active_masteries(entity, weapon: dict | None) -> list[str]:
    return [m for m in weapon_masteries(weapon) if can_use_mastery(entity, weapon, m)]


def attack_ability_mod(source, weapon: dict | None) -> int:
    """Ability modifier used for the attack (STR, or DEX for finesse/ranged)."""
    if weapon is None:
        return source.str_mod()
    props = weapon.get("properties") or []
    if weapon.get("type") == "ranged_attack" or "finesse" in props:
        if "finesse" in props:
            return max(source.str_mod(), source.dex_mod())
        return source.dex_mod()
    return source.str_mod()


def _entity_uid(entity):
    return getattr(entity, "entity_uid", None) or id(entity)


def _iter_battle_entities(battle):
    if battle is None:
        return []
    ents = getattr(battle, "entities", None)
    if ents is not None:
        try:
            return list(ents.keys())
        except Exception:
            pass
    return list(getattr(battle, "combat_order", None) or [])


def _controller_prompts(controller) -> bool:
    """True when the controller will yield for a player (WebController)."""
    if controller is None:
        return False
    try:
        from natural20.web.web_controller import WebController
        if isinstance(controller, WebController):
            return True
    except Exception:
        pass
    select = getattr(controller, "select_reaction", None)
    if inspect.isgeneratorfunction(select):
        return True
    base = getattr(controller, "base", None)
    if base is not None and base is not controller:
        return _controller_prompts(base)
    return False


def _wants_optional_mastery(action, battle, mastery: str) -> bool:
    """Prompt Web players; AI / no-controller auto-accepts. ``no-reaction`` skips."""
    source = action.source
    reaction_type = f"weapon_mastery_{mastery}"
    stored = action.has_async_reaction_for_source(source, reaction_type)
    if stored is None:
        return False
    if stored is not False:
        if isinstance(stored, WeaponMasteryChoice):
            return bool(stored.use)
        return bool(stored)

    if battle is None:
        return True
    controller = battle.controller_for(source)
    if not _controller_prompts(controller):
        return True

    yes = WeaponMasteryChoice(source.session, source, mastery, use=True)
    no = WeaponMasteryChoice(source.session, source, mastery, use=False)
    event_payload = {
        "type": reaction_type,
        "trigger": reaction_type,
        "source": source,
        "target": getattr(action, "target", None),
        "mastery": mastery,
    }
    selected = controller.select_reaction(
        source,
        battle,
        battle.map_for(source),
        [yes, no],
        event_payload,
    )
    if inspect.isgenerator(selected):
        raise AsyncReactionHandler(source, selected, action, reaction_type)
    if selected is None:
        return False
    if isinstance(selected, WeaponMasteryChoice):
        return bool(selected.use)
    return True


def resolve_mastery_on_hit(action, battle, target, weapon, hit: bool, damage) -> list[dict]:
    """Return result items for mastery effects after hit/miss is known.

    Push/Topple are optional (RAW “you can”) and prompt web players.
    Cleave/Nick are skipped in this slice (need a second attack / TWF rewrite).
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
            if size_ok and _wants_optional_mastery(action, battle, "push"):
                results.append({
                    "type": "weapon_mastery_push",
                    "source": source,
                    "target": target,
                    "distance": 10,
                    "weapon": weapon,
                })

        if can_use_mastery(source, weapon, "sap"):
            target._sap_next_attack = True  # noqa: SLF001
            target._sap_from = _entity_uid(source)  # noqa: SLF001
            results.append({
                "type": "weapon_mastery_sap",
                "source": source,
                "target": target,
                "weapon": weapon,
            })

        if can_use_mastery(source, weapon, "vex"):
            uid = _entity_uid(target)
            vex_map = getattr(source, "_vex_advantage_vs", None)
            if vex_map is None:
                source._vex_advantage_vs = {}  # noqa: SLF001
                vex_map = source._vex_advantage_vs
            vex_map[str(uid)] = True
            source._vex_applied_this_turn = True  # noqa: SLF001
            results.append({
                "type": "weapon_mastery_vex",
                "source": source,
                "target": target,
                "weapon": weapon,
            })

        if can_use_mastery(source, weapon, "slow") and damage is not None:
            target._mastery_slow_ft = 10  # noqa: SLF001
            target._mastery_slow_from = _entity_uid(source)  # noqa: SLF001
            results.append({
                "type": "weapon_mastery_slow",
                "source": source,
                "target": target,
                "speed_reduction": 10,
                "weapon": weapon,
            })

        if can_use_mastery(source, weapon, "topple") and _wants_optional_mastery(action, battle, "topple"):
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


def apply_speed_reduction(entity, speed):
    """Subtract Slow mastery from a computed speed value."""
    try:
        value = int(speed or 0)
    except (TypeError, ValueError):
        value = 0
    slow_ft = int(getattr(entity, "_mastery_slow_ft", 0) or 0)
    if slow_ft:
        return max(0, value - slow_ft)
    return speed


def consume_sap_disadvantage(target) -> bool:
    if getattr(target, "_sap_next_attack", False):
        target._sap_next_attack = False
        target._sap_from = None
        return True
    return False


def consume_vex_advantage(source, target) -> bool:
    vex_map = getattr(source, "_vex_advantage_vs", None)
    if not vex_map:
        return False
    uid = str(_entity_uid(target))
    if vex_map.pop(uid, False):
        return True
    # Legacy keys stored as raw uid / id()
    raw = _entity_uid(target)
    if vex_map.pop(raw, False):
        return True
    return False


def expire_mastery_start_of_turn(entity, battle=None) -> None:
    """Clear Slow/Sap this attacker applied (until the start of their next turn)."""
    uid = _entity_uid(entity)
    for other in _iter_battle_entities(battle):
        if getattr(other, "_mastery_slow_from", None) == uid:
            other._mastery_slow_ft = 0
            other._mastery_slow_from = None
        if getattr(other, "_sap_from", None) == uid:
            other._sap_next_attack = False
            other._sap_from = None


def expire_mastery_end_of_turn(entity, battle=None) -> None:
    """Vex lasts until the end of the attacker's next turn (idempotent per turn)."""
    turn_key = None
    if battle is not None:
        turn_key = (
            id(battle),
            getattr(battle, "round", 0),
            getattr(battle, "current_turn_index", 0),
        )
        if getattr(entity, "_vex_expire_turn_key", None) == turn_key:
            return
        entity._vex_expire_turn_key = turn_key  # noqa: SLF001

    if getattr(entity, "_vex_applied_this_turn", False):
        entity._vex_applied_this_turn = False
        return
    entity._vex_advantage_vs = {}


def clear_mastery_state(entity) -> None:
    entity._sap_next_attack = False
    entity._sap_from = None
    entity._vex_advantage_vs = {}
    entity._vex_applied_this_turn = False
    entity._mastery_slow_ft = 0
    entity._mastery_slow_from = None


def mastery_state_to_dict(entity) -> dict:
    vex_map = getattr(entity, "_vex_advantage_vs", None) or {}
    return {
        "_sap_next_attack": bool(getattr(entity, "_sap_next_attack", False)),
        "_sap_from": getattr(entity, "_sap_from", None),
        "_vex_advantage_vs": {str(k): bool(v) for k, v in vex_map.items()},
        "_vex_applied_this_turn": bool(getattr(entity, "_vex_applied_this_turn", False)),
        "_mastery_slow_ft": int(getattr(entity, "_mastery_slow_ft", 0) or 0),
        "_mastery_slow_from": getattr(entity, "_mastery_slow_from", None),
    }


def mastery_state_from_dict(entity, data: dict | None) -> None:
    if not data:
        return
    entity._sap_next_attack = bool(data.get("_sap_next_attack", False))
    entity._sap_from = data.get("_sap_from")
    vex = data.get("_vex_advantage_vs") or {}
    entity._vex_advantage_vs = {str(k): bool(v) for k, v in vex.items()}
    entity._vex_applied_this_turn = bool(data.get("_vex_applied_this_turn", False))
    entity._mastery_slow_ft = int(data.get("_mastery_slow_ft", 0) or 0)
    entity._mastery_slow_from = data.get("_mastery_slow_from")
