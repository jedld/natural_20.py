"""NPC innate spellcasting from YAML (monster stat-block "Spellcasting").

    innate_spellcasting:
      ability: charisma          # casting ability
      dc: 14                     # optional fixed save DC (else 8 + PB + mod)
      attack: 6                  # optional fixed spell attack bonus (else PB + mod)
      no_material: true          # ignore consumed material components
      at_will: [mage_hand, invisibility]
      per_day:
        2: [disguise_self, dimension_door, sending]
        1: [dominate_person]

The spells are always prepared, cast at their own level and paid from the
``free_casts`` machinery (``natural20/utils/class_mechanics.py``): at-will
spells need nothing, per-day spells spend a ``innate:<spell>`` resource pool
restored on a long rest.
"""

from __future__ import annotations

KEY = 'innate_spellcasting'


def innate_config(entity):
    props = getattr(entity, 'properties', None) or {}
    config = props.get(KEY)
    return config if isinstance(config, dict) else None


def pool_name(spell_slug):
    return f"innate:{spell_slug}"


def _per_day(config):
    entries = []
    for uses, spells in (config.get('per_day') or {}).items():
        try:
            count = int(uses)
        except (TypeError, ValueError):
            continue
        if isinstance(spells, str):
            spells = [spells]
        for slug in spells or []:
            if slug:
                entries.append((str(slug), count))
    return entries


def innate_spells(entity):
    """Every innate spell slug (at will first, then per-day)."""
    config = innate_config(entity)
    if not config:
        return []
    out = []
    at_will = config.get('at_will') or []
    if isinstance(at_will, str):
        at_will = [at_will]
    for slug in list(at_will) + [s for s, _ in _per_day(config)]:
        if slug and slug not in out:
            out.append(str(slug))
    return out


def innate_spell_groups(entity):
    """``[('at_will', None, [slugs]), ('per_day', 2, [slugs]), ...]`` for display."""
    config = innate_config(entity)
    if not config:
        return []
    at_will = config.get('at_will') or []
    if isinstance(at_will, str):
        at_will = [at_will]
    groups = [('at_will', None, [str(s) for s in at_will])] if at_will else []
    by_count = {}
    for slug, count in _per_day(config):
        by_count.setdefault(count, []).append(slug)
    for count in sorted(by_count, reverse=True):
        groups.append(('per_day', count, by_count[count]))
    return groups


def innate_free_cast_specs(entity):
    """``free_casts``-style specs for the innate spells."""
    config = innate_config(entity)
    if not config:
        return []
    specs = []
    at_will = config.get('at_will') or []
    if isinstance(at_will, str):
        at_will = [at_will]
    for slug in at_will:
        specs.append({'spell': str(slug), 'at_will': True, 'innate': True})
    for slug, _count in _per_day(config):
        specs.append({'spell': slug, 'pool': pool_name(slug), 'innate': True})
    return specs


def ensure_innate_pools(entity):
    """Register the per-day pools; spent uses survive a reload."""
    config = innate_config(entity)
    if not config or not hasattr(entity, 'register_resource'):
        return
    for slug, count in _per_day(config):
        name = pool_name(slug)
        existing = entity.get_resource(name) if hasattr(entity, 'get_resource') else None
        if existing is None:
            entity.register_resource(name, count, restore_on='long_rest')
        elif existing.max_value != count:
            entity.register_resource(name, count, restore_on='long_rest',
                                     current=min(count, existing.current))


def innate_ability(entity, spell_slug=None):
    config = innate_config(entity)
    if not config:
        return None
    if spell_slug is not None and spell_slug not in innate_spells(entity):
        return None
    from natural20.entity_class.data_driven import normalize_ability
    return normalize_ability(config.get('ability') or 'charisma')


def innate_save_dc(entity):
    config = innate_config(entity)
    if not config:
        return None
    if config.get('dc') is not None:
        return int(config['dc'])
    ability = innate_ability(entity)
    return 8 + int(entity.proficiency_bonus()) + int(entity.ability_mod(ability) or 0)


def innate_attack_bonus(entity):
    config = innate_config(entity)
    if not config:
        return None
    if config.get('attack') is not None:
        return int(config['attack'])
    ability = innate_ability(entity)
    return int(entity.proficiency_bonus()) + int(entity.ability_mod(ability) or 0)


def ignores_materials(entity, spell_slug):
    config = innate_config(entity)
    return bool(config and config.get('no_material') and spell_slug in innate_spells(entity))
