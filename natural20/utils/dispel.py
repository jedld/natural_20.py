"""Spells active *on* a creature, for Dispel Magic and similar effects.

SRD Dispel Magic: "Any spell of 3rd level or lower on the target ends. For
each spell of 4th level or higher on the target, make an ability check using
your spellcasting ability. The DC equals 10 + the spell's level."

A spell is "on" a creature when it is the target of the spell (Bless,
Polymorph, Hold Person, ...) or the spell targets its caster (Shield, Mirror
Image, Spirit Guardians). Spells a creature cast on *others* are not on it.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Tuple


def _is_spell(effect) -> bool:
    from natural20.spell.spell import Spell
    return isinstance(effect, Spell)


def _targets_of(entry_target) -> list:
    if entry_target is None:
        return []
    if isinstance(entry_target, (list, tuple)):
        return [t for t in entry_target if hasattr(t, 'entity_uid')]
    return [entry_target] if hasattr(entry_target, 'entity_uid') else []


def spell_level(effect) -> int:
    action = getattr(effect, 'action', None)
    level = getattr(action, 'at_level', None) if action is not None else None
    if level is None:
        level = (getattr(effect, 'properties', None) or {}).get('level', 0)
    try:
        return int(level or 0)
    except (TypeError, ValueError):
        return 0


def _casters(target, battle) -> Iterable:
    seen = set()
    candidates = [target]
    if battle is not None:
        candidates.extend(list(getattr(battle, 'entities', {}) or {}))
    for c in candidates:
        if id(c) in seen or not hasattr(c, 'casted_effects'):
            continue
        seen.add(id(c))
        yield c


def spells_on(target, battle=None) -> List[Tuple[object, object]]:
    """``[(spell_effect, caster), ...]`` for every leveled spell on ``target``."""
    found = {}

    for descriptors in (getattr(target, 'effects', None) or {}).values():
        for d in descriptors or []:
            effect = d.get('effect')
            if _is_spell(effect) and spell_level(effect) > 0:
                found.setdefault(id(effect), (effect, d.get('source') or getattr(effect, 'source', None)))

    for caster in _casters(target, battle):
        for entry in list(getattr(caster, 'casted_effects', None) or []):
            effect = entry.get('effect')
            if not _is_spell(effect) or spell_level(effect) <= 0:
                continue
            if any(t is target for t in _targets_of(entry.get('target'))):
                found.setdefault(id(effect), (effect, caster))

    return list(found.values())


def end_spell_on(target, effect, caster=None) -> None:
    """End ``effect`` on ``target``; a single-target concentration spell ends outright."""
    caster = caster or getattr(effect, 'source', None)
    action = getattr(effect, 'action', None)
    spell_targets = _targets_of(getattr(action, 'target', None)) if action is not None else []
    concentrating = caster is not None and getattr(caster, 'concentration', None) is effect
    if concentrating and (caster is target or len(spell_targets) <= 1):
        caster.dismiss_effect(effect)
        return
    target.remove_effect(effect)
    from natural20.utils import polymorph
    if getattr(effect, 'id', None) == 'polymorph' and polymorph.is_polymorphed(target):
        polymorph.revert(target, reason='dispelled')


def worth_dispelling(battle, entity, target) -> bool:
    """AI: is there a spell on ``target`` that ``entity`` wants gone?

    Any spell cast by one of ``entity``'s opponents: a debuff on an ally or
    a buff on a foe.
    """
    if target is None or battle is None:
        return False
    for _effect, caster in spells_on(target, battle):
        if caster is None or caster is entity:
            continue
        try:
            if battle.opposing(entity, caster):
                return True
        except Exception:
            continue
    return False


def creature_target(target) -> Optional[object]:
    if isinstance(target, (list, tuple)):
        creatures = [t for t in target if hasattr(t, 'register_effect')]
        return creatures[0] if creatures else None
    return target if hasattr(target, 'register_effect') else None
