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


# --- magical effects on the map (PersistentAoEZone) -----------------------
#
# SRD Dispel Magic: "Choose one creature, object, or magical effect within
# range." Persistent spell zones (Spike Growth, Web, Cloudkill, Grease,
# Sleet Storm, …) are targetable magical effects: either the zone itself,
# one of its zone-tile markers, or the square the zone covers.

def _live_zones(battle, battle_map) -> list:
    """All live persistent zones from the battle and/or the map ticking."""
    zones = []
    if battle is not None:
        zones.extend(getattr(battle, 'active_zones', None) or [])
    if battle_map is not None:
        zones.extend(getattr(battle_map, 'environment_zones', None) or [])
    seen = set()
    live = []
    for zone in zones:
        if zone is None or id(zone) in seen:
            continue
        seen.add(id(zone))
        if getattr(zone, '_dismissed', False) or not hasattr(zone, 'contains'):
            continue
        live.append(zone)
    return live


def zones_at(battle, battle_map, pos) -> list:
    """Live spell zones on ``battle_map`` whose area covers square ``pos``."""
    try:
        pos = (int(pos[0]), int(pos[1]))
    except (TypeError, ValueError):
        return []
    found = []
    for zone in _live_zones(battle, battle_map):
        zone_map = getattr(zone, 'map', None)
        if battle_map is not None and zone_map is not None and zone_map is not battle_map:
            continue
        try:
            if zone.contains(pos):
                found.append(zone)
        except Exception:
            continue
    return found


def zone_for_target(target, battle=None, battle_map=None, effect_id=None) -> Optional[object]:
    """Resolve a Dispel Magic target to the zone it points at.

    Accepts the zone itself, a zone-tile marker (anything with a ``zone``
    attribute), or an ``[x, y]`` square. ``effect_id`` selects a specific
    zone when several overlap the square (the client's effect picker).
    """
    if target is None:
        return None
    if effect_id:
        for zone in _live_zones(battle, battle_map):
            if str(getattr(zone, 'id', '')) == str(effect_id):
                return zone
        return None
    if hasattr(target, 'contains') and hasattr(target, 'squares'):
        return target if not getattr(target, '_dismissed', False) else None
    zone = getattr(target, 'zone', None)
    if zone is not None and not getattr(zone, '_dismissed', False):
        return zone
    if isinstance(target, (list, tuple)) and len(target) == 2 \
            and all(isinstance(v, int) for v in target):
        zones = zones_at(battle, battle_map, target)
        return zones[0] if zones else None
    return None


def _zone_effect_entries(zone) -> list:
    """Owner-side effect descriptors tied to this exact zone (if any)."""
    owner = getattr(zone, 'owner', None)
    if owner is None:
        return []
    entries = list(getattr(owner, 'casted_effects', None) or [])
    for descriptors in (getattr(owner, 'effects', None) or {}).values():
        entries.extend(descriptors or [])
    for hooks in (getattr(owner, 'entity_event_hooks', None) or {}).values():
        entries.extend(hooks or [])
    return [
        entry for entry in entries
        if entry is not None
        and (entry.get('target') is zone
             or getattr(entry.get('effect'), 'zone', None) is zone)
    ]


def zone_spell_level(zone, session=None) -> int:
    """Spell level of the zone's casting spell (0 when unknown).

    Prefers the owner-side effect entry so an upcast zone (Spike Growth
    cast at 4th level) reports the level Dispel Magic must check against."""
    for entry in _zone_effect_entries(zone):
        try:
            level = spell_level(entry['effect'])
        except Exception:
            continue
        if level > 0:
            return level
    spell = getattr(zone, 'spell', None)
    if isinstance(spell, dict):
        if spell.get('level') is not None:
            try:
                return int(spell.get('level'))
            except (TypeError, ValueError):
                pass
    elif spell is not None:
        # spell_level() prefers the cast action's at_level (upcasts).
        try:
            level = spell_level(spell)
        except Exception:
            level = 0
        if level > 0:
            return level
    # Zone names usually match the spell slug (spike_growth, web, ...).
    if session is not None:
        meta = (getattr(session, 'spells', None) or {}).get(getattr(zone, 'name', ''))
        if isinstance(meta, dict) and meta.get('level') is not None:
            try:
                return int(meta.get('level'))
            except (TypeError, ValueError):
                pass
    return 0


def zone_label(zone) -> str:
    spell = getattr(zone, 'spell', None)
    props = spell.get if isinstance(spell, dict) else getattr(spell, 'properties', None)
    get = props.get if hasattr(props, 'get') else None
    if get:
        label = get('label') or get('name')
        if label:
            return str(label)
    return str(getattr(zone, 'name', 'magical effect') or 'magical effect').replace('_', ' ').title()


def end_spell_zone(zone) -> bool:
    """End a persistent zone the generic way.

    Prefers dismissing the caster-side effect tied to this exact zone (drops
    concentration and runs the spell's own dismiss hook, which removes tiles
    and unregisters the zone); force-dismisses the zone when no owner-side
    effect entry is found.
    """
    owner = getattr(zone, 'owner', None)
    if owner is not None:
        entries = list(getattr(owner, 'casted_effects', None) or [])
        for descriptors in (getattr(owner, 'effects', None) or {}).values():
            entries.extend(descriptors or [])
        for hooks in (getattr(owner, 'entity_event_hooks', None) or {}).values():
            entries.extend(hooks or [])
        for entry in entries:
            if entry is None:
                continue
            effect = entry.get('effect')
            if entry.get('target') is zone or getattr(effect, 'zone', None) is zone:
                owner.dismiss_effect(effect)
                break
    if not getattr(zone, '_dismissed', False):
        zone.dismiss()
        return True
    return True
