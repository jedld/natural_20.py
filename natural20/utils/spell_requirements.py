"""Spell YAML requirements beyond slots and casting time.

``consumed_materials`` lists costly components the spell uses up (SRD
"which the spell consumes")::

    consumed_materials:
      - {item: diamond, qty: 1}

``requires`` lists environment conditions the cast needs:

* ``outdoors`` / ``indoors`` — map ``outdoors`` property (``sunlight`` maps
  count as outdoors), same rule as monster summons.
* ``open_sky`` — outdoors, or a map ``ceiling_height`` (feet) of at least the
  spell's ``min_ceiling_ft`` (default 100), e.g. Call Lightning's storm cloud.
* ``out_of_combat`` — not castable while a battle is ongoing (Rope Trick).

Spells with a ``verbal`` component can't be cast by a caster standing in a
magical silence (``natural20/utils/silence.py``).

Spells cast from a scroll ignore material components.
"""

from __future__ import annotations

from typing import List, Optional

STORM_WEATHER = ('storm', 'stormy', 'thunderstorm', 'lightning')


def _materials(spell_details) -> List[dict]:
    entries = (spell_details or {}).get('consumed_materials') or []
    out = []
    for entry in entries:
        if isinstance(entry, str):
            out.append({'item': entry, 'qty': 1})
        elif isinstance(entry, dict) and entry.get('item'):
            out.append({'item': entry['item'], 'qty': int(entry.get('qty', 1) or 1)})
    return out


def missing_materials(entity, spell_details) -> List[str]:
    """Item ids the caster lacks for ``spell_details``' consumed materials."""
    missing = []
    from natural20.utils.innate_spellcasting import ignores_materials
    if ignores_materials(entity, (spell_details or {}).get('id')):
        return missing
    for entry in _materials(spell_details):
        count = entity.item_count(entry['item']) if hasattr(entity, 'item_count') else 0
        if count < entry['qty']:
            missing.append(entry['item'])
    return missing


def consume_materials(entity, spell_details) -> None:
    from natural20.utils.innate_spellcasting import ignores_materials
    if ignores_materials(entity, (spell_details or {}).get('id')):
        return
    for entry in _materials(spell_details):
        if hasattr(entity, 'deduct_item'):
            entity.deduct_item(entry['item'], entry['qty'])


def _map_for(entity, battle=None, battle_map=None):
    if battle_map is not None:
        return battle_map
    if battle is not None:
        try:
            found = battle.map_for(entity)
            if found is not None:
                return found
        except Exception:
            pass
    session = getattr(entity, 'session', None)
    if session is not None and hasattr(session, 'maps_for_entity'):
        try:
            maps = session.maps_for_entity(entity)
            if maps:
                return maps[0]
        except Exception:
            pass
    return None


def _map_props(battle_map) -> dict:
    return (getattr(battle_map, 'properties', None) or {}) if battle_map is not None else {}


def has_open_sky(entity, spell_details=None, battle=None, battle_map=None) -> bool:
    from natural20.utils.summons import is_outdoors
    current = _map_for(entity, battle, battle_map)
    if current is None or is_outdoors(entity, battle, current):
        return True
    ceiling = _map_props(current).get('ceiling_height')
    try:
        need = int((spell_details or {}).get('min_ceiling_ft', 100))
        return ceiling is not None and int(ceiling) >= need
    except (TypeError, ValueError):
        return False


def environment_issue(entity, spell_details, battle=None, battle_map=None) -> Optional[str]:
    """Why the spell's ``requires`` list (or a magical silence around the
    caster, for spells with a verbal component) blocks casting here, or None."""
    from natural20.utils.summons import is_outdoors
    from natural20.utils.silence import has_verbal_component
    if has_verbal_component(spell_details):
        from natural20.utils.message_spell_path import entity_in_magical_silence
        caster = entity.owner if hasattr(entity, 'familiar') and entity.familiar() else entity
        if entity_in_magical_silence(caster):
            return 'silenced'
    requirements = (spell_details or {}).get('requires') or []
    if not requirements:
        return None
    if 'out_of_combat' in requirements and battle is not None and battle.ongoing():
        return 'not usable in combat'
    current = _map_for(entity, battle, battle_map)
    if current is None:
        return None
    for requirement in requirements:
        if requirement == 'outdoors' and not is_outdoors(entity, battle, current):
            return 'not outdoors'
        if requirement == 'indoors' and is_outdoors(entity, battle, current):
            return 'not indoors'
        if requirement == 'open_sky' and not has_open_sky(entity, spell_details, battle, current):
            return 'no open sky overhead'
    return None


def spells_this_turn_issue(entity, battle, spell_level, resource) -> Optional[str]:
    """Why another action/bonus-action spell can't be cast this turn, or None.

    2014 (``bonus_action_spell``): once a bonus-action spell is cast, the only
    other spell allowed is a 1-action cantrip, in either order. 2024
    (``one_slot_per_turn``): only one spell slot may be spent per turn.
    """
    if battle is None or resource not in ('action', 'bonus_action'):
        return None
    state = battle.entity_state_for(entity) or {}
    cast = state.get('casted_spells')
    if cast is None:
        cast = [{'level': 1, 'resource': 'action'} for _ in state.get('casted_level_spells') or []]
    if not cast:
        return None
    spell_level = int(spell_level or 0)
    ruleset = getattr(getattr(entity, 'session', None), 'ruleset', None)
    try:
        model = ruleset.spells_per_turn_model() if ruleset is not None else 'bonus_action_spell'
    except Exception:
        model = 'bonus_action_spell'
    if model == 'one_slot_per_turn':
        if spell_level > 0 and any(int(c.get('level') or 0) > 0 for c in cast):
            return 'already spent a spell slot this turn'
        return None
    if resource == 'bonus_action':
        if any(not (c.get('resource') == 'action' and int(c.get('level') or 0) == 0) for c in cast):
            return 'a bonus-action spell needs every other spell this turn to be a 1-action cantrip'
        return None
    if spell_level > 0 and any(c.get('resource') == 'bonus_action' for c in cast):
        return 'after a bonus-action spell only a 1-action cantrip can be cast'
    return None


def is_stormy(battle_map) -> bool:
    """Map YAML ``stormy: true``, ``weather: storm``, or a storm ``default_effect``."""
    props = _map_props(battle_map)
    if props.get('stormy'):
        return True
    weather = str(props.get('weather') or '').lower()
    if weather and any(word in weather for word in STORM_WEATHER):
        return True
    effects = []
    for key in ('default_effect', 'default_effects'):
        raw = props.get(key)
        if isinstance(raw, dict):
            effects.append(raw)
        elif isinstance(raw, (list, tuple)):
            effects.extend(e for e in raw if isinstance(e, dict))
    for effect in effects:
        name = str(effect.get('effect') or '').lower()
        if any(word in name for word in STORM_WEATHER):
            return True
    return False
