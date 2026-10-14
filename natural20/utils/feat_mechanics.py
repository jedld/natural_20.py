"""Generic mechanics declared in feat YAML (``feats/<id>.yml``).

Feat files load through ``load_campaign_resource_path`` (campaign -> imports
-> expansion packs -> ruleset overlay -> ``templates/``), so SRD feats live in
``templates/feats`` and non-SRD feats in an expansion pack. A feat id on the
sheet's ``feats`` list with no YAML file is a no-op here. The same blocks may
also sit directly in a creature's own properties (NPC YAML).

``resource_pools`` — limited-use pools, registered on first use::

    resource_pools:
      luck_points: {max: proficiency_bonus, restore_on: long_rest}

``weapon_attack_rules`` — exceptions to the normal weapon-attack rules. Each
rule applies to weapons matching its ``weapons`` filter (``type``:
melee_attack | ranged_attack, ``weapon_type``: a word in the weapon id/name
such as ``crossbow``, ``property``/``properties``: weapon properties that must
all be present). Spells never match::

    weapon_attack_rules:
      - weapons: {type: ranged_attack}
        ignore_cover: [half, three_quarters]
        no_long_range_disadvantage: true
        no_adjacent_enemy_disadvantage: true
      - weapons: {weapon_type: crossbow}
        ignore_properties: [loading]
      - weapons: {weapon_type: crossbow, property: light}
        extra_attack_ability_damage: true   # Light-property extra attack adds the modifier

``free_casts`` — same entries as class YAML ``free_casts``
(``natural20/utils/class_mechanics.py``); a feat's pool comes from its
``resource_pools``. ``spell_source: spell_abilities`` plus ``spell_level``
picks the spell from the sheet's ``spell_abilities`` map (the spells a feat
granted), for example Magic Initiate's level 1 spell.

``luck`` — see ``natural20/utils/luck_points.py``.
"""

from __future__ import annotations

COVER_AC = {'half': 2, 'three_quarters': 5, 'three_quarter': 5}


def feat_definitions(entity):
    """``[(feat_id, definition)]`` for the entity's feats that have YAML."""
    from natural20.utils.attack_options import _feat_definition
    props = getattr(entity, 'properties', None) or {}
    session = getattr(entity, 'session', None)
    if session is None:
        return []
    out = []
    for feat in props.get('feats') or []:
        definition = _feat_definition(session, str(feat))
        if isinstance(definition, dict):
            out.append((str(feat), definition))
    return out


def _as_entries(block):
    if isinstance(block, dict):
        return [dict(spec or {}, id=spec_id) for spec_id, spec in block.items() if isinstance(spec, dict)]
    if isinstance(block, list):
        return [spec for spec in block if isinstance(spec, dict)]
    return []


def feat_specs(entity, key):
    """``(feat_id, spec)`` for every ``key`` entry from feats and the creature's own YAML."""
    out = []
    for feat_id, definition in feat_definitions(entity):
        for spec in _as_entries(definition.get(key)):
            out.append((feat_id, spec))
    props = getattr(entity, 'properties', None) or {}
    for spec in _as_entries(props.get(key)):
        out.append((None, spec))
    return out


def has_benefit(entity, benefit):
    """True when a feat's ``benefits`` list, or a class YAML ``benefits`` entry
    (``{feature: eldritch_mind, benefit: concentration_advantage}``) whose feature
    the creature has, grants ``benefit``."""
    for _feat_id, definition in feat_definitions(entity):
        if benefit in (definition.get('benefits') or []):
            return True
    try:
        from natural20.utils.class_mechanics import class_specs
        for _klass, spec in class_specs(entity, 'benefits'):
            if spec.get('benefit') == benefit:
                return True
    except Exception:
        pass
    return False


def ensure_feat_pools(entity):
    """Register feat ``resource_pools``; spent uses survive a larger maximum."""
    if not hasattr(entity, 'register_resource'):
        return
    from natural20.entity_class.data_driven import resolve_pool_max
    for feat_id, definition in feat_definitions(entity):
        for name, spec in ((definition.get('resource_pools') or {})).items():
            if not isinstance(spec, dict):
                continue
            new_max = resolve_pool_max(entity, spec)
            restore_on = spec.get('restore_on') or spec.get('recharge') or 'long_rest'
            existing = entity.get_resource(name)
            if existing is None:
                entity.register_resource(name, new_max, restore_on=restore_on)
            elif existing.max_value != new_max:
                gained = max(0, new_max - existing.max_value)
                entity.register_resource(name, new_max, restore_on=restore_on,
                                         current=min(new_max, existing.current + gained))


# ---------------------------------------------------------------------------
# Weapon attack rules
# ---------------------------------------------------------------------------

def _weapon_words(weapon):
    words = set()
    for key in ('id', 'weapon_type', 'category', 'name', '_inventory_key'):
        value = weapon.get(key)
        if value:
            words.add(str(value).lower().replace(' ', '_'))
    return words


def is_weapon(weapon):
    """True for weapons and NPC weapon attacks, False for spells."""
    if not isinstance(weapon, dict):
        return False
    return not any(key in weapon for key in ('school', 'spell_class', 'spell_list_classes'))


def weapon_matches(weapon, filt, thrown=False):
    if not is_weapon(weapon):
        return False
    if not filt or filt is True:
        return True
    if not isinstance(filt, dict):
        return False
    attack_type = filt.get('type')
    if attack_type and weapon.get('type') != attack_type:
        return False
    if thrown and attack_type == 'ranged_attack':
        return False
    weapon_type = filt.get('weapon_type')
    if weapon_type:
        needle = str(weapon_type).lower()
        if not any(needle in word for word in _weapon_words(weapon)):
            return False
    required = filt.get('properties') or []
    if filt.get('property'):
        required = list(required) + [filt['property']]
    props = weapon.get('properties') or []
    return all(p in props for p in required)


def weapon_rules(entity, weapon, thrown=False):
    """Rules from ``weapon_attack_rules`` that apply to ``weapon``."""
    if entity is None or not is_weapon(weapon):
        return []
    return [spec for _feat, spec in feat_specs(entity, 'weapon_attack_rules')
            if weapon_matches(weapon, spec.get('weapons'), thrown=thrown)]


def has_weapon_rule(entity, weapon, key, thrown=False):
    return any(spec.get(key) for spec in weapon_rules(entity, weapon, thrown=thrown))


def ignored_cover_ac(entity, weapon, thrown=False):
    """Highest cover AC bonus the attacker ignores with this weapon (0 = none)."""
    best = 0
    for spec in weapon_rules(entity, weapon, thrown=thrown):
        for level in spec.get('ignore_cover') or []:
            best = max(best, COVER_AC.get(str(level), 0))
    return best


def ignores_weapon_property(entity, weapon, prop):
    return any(prop in (spec.get('ignore_properties') or [])
               for spec in weapon_rules(entity, weapon))


def no_long_range_disadvantage(entity, weapon, thrown=False):
    return has_weapon_rule(entity, weapon, 'no_long_range_disadvantage', thrown=thrown)


def no_adjacent_enemy_disadvantage(entity, weapon, thrown=False):
    return has_weapon_rule(entity, weapon, 'no_adjacent_enemy_disadvantage', thrown=thrown)


def extra_attack_adds_ability(entity, weapon):
    return has_weapon_rule(entity, weapon, 'extra_attack_ability_damage')
