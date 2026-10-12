"""Who killed a creature and how, recorded on the entity for later consumers.

``Entity.take_damage`` calls :func:`record_damage` for every damaging blow and
:func:`note_downed` when a creature drops to 0 HP; ``Entity.make_dead`` stores
:func:`build_death_info` under ``attributes['death_info']`` and attaches it to
the ``died`` event. Values are plain primitives so save/load round-trips.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

def _attack_label(item: Dict[str, Any]) -> Optional[str]:
    spell = item.get('spell')
    if isinstance(spell, dict) and spell.get('name'):
        return str(spell['name'])
    name = item.get('attack_name')
    if name:
        return str(name)
    weapon = item.get('weapon')
    if isinstance(weapon, dict):
        return weapon.get('name')
    if weapon:
        return str(weapon)
    return None


def record_damage(entity, item, *, damage: int, damage_type, critical: bool, battle=None) -> None:
    """Remember the latest damaging blow (source + attack) on ``entity``."""
    if not isinstance(item, dict) or damage <= 0:
        return
    source = item.get('source')
    if source is None or source is entity:
        return
    label = _attack_label(item)
    entry = {
        'killer_uid': getattr(source, 'entity_uid', None),
        'killer_name': getattr(source, 'name', None),
        'attack_name': str(label).replace('_', ' ') if label else None,
        'kind': 'spell' if item.get('type') == 'spell_damage' else 'attack',
        'damage': int(damage),
        'damage_type': str(damage_type) if damage_type else None,
        'critical': bool(critical),
    }
    if battle is not None:
        entry['round'] = int(getattr(battle, 'round', 0) or 0)
    entity.attributes['last_damage'] = entry


def note_downed(entity) -> None:
    last = entity.attributes.get('last_damage')
    if isinstance(last, dict):
        entity.attributes['downed_by'] = dict(last)


def clear_downed(entity) -> None:
    entity.attributes.pop('downed_by', None)


def build_death_info(entity, cause: Optional[str]) -> Dict[str, Any]:
    if cause == 'failed_death_saves':
        blow = entity.attributes.get('downed_by') or entity.attributes.get('last_damage')
    else:
        blow = entity.attributes.get('last_damage')
    info: Dict[str, Any] = {
        'victim_uid': getattr(entity, 'entity_uid', None),
        'victim_name': getattr(entity, 'name', None),
        'cause': cause or 'unknown',
    }
    if cause and isinstance(blow, dict):
        info.update(blow)
    return info


def describe_death(info: Dict[str, Any], *, killer_pov: bool = False) -> str:
    """One-sentence description, e.g. for prompts. ``killer_pov`` addresses the killer as 'you'."""
    victim = info.get('victim_name') or 'the victim'
    killer = 'you' if killer_pov else (info.get('killer_name') or 'an unknown foe')
    how = info.get('attack_name')
    dmg = info.get('damage')
    dtype = info.get('damage_type')
    blow = ''
    if how:
        blow = f" with {how}"
    if dmg:
        blow += f" ({dmg} {dtype + ' ' if dtype else ''}damage{', a critical hit' if info.get('critical') else ''})"
    cause = info.get('cause')
    if cause == 'failed_death_saves':
        return f"{victim} bled out and died after {killer} struck them down{blow}."
    if cause == 'massive_damage':
        return f"{killer.capitalize()} killed {victim} outright{blow} — the blow was so massive they died instantly."
    if cause == 'damage_while_dying':
        return f"{killer.capitalize()} finished off {victim}{blow} while they lay dying."
    return f"{killer.capitalize()} killed {victim}{blow}."
