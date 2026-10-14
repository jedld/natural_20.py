"""Extra damage that class features add to every qualifying weapon hit.

Each entry uses the same shape as weapon/NPC ``additional_damage`` riders, so
``AttackAction._on_hit_riders`` resolves them through the shared
``additional_damage`` path (crit dice, Uncanny Dodge halving, combat log).

Features that grant the same rider (2014 Improved Divine Smite and 2024
Radiant Strikes) never stack: one entry per ``group``.
"""

from __future__ import annotations

FEATURE_HIT_RIDERS = {
    'improved_divine_smite': {
        'group': 'paladin_radiant_strikes', 'damage_die': '1d8', 'damage_type': 'radiant', 'melee_only': True,
    },
    'radiant_strikes': {
        'group': 'paladin_radiant_strikes', 'damage_die': '1d8', 'damage_type': 'radiant', 'melee_only': True,
    },
}


def _is_melee_weapon_attack(weapon, thrown=False):
    if not isinstance(weapon, dict) or thrown:
        return False
    return weapon.get('type') == 'melee_attack'


def feature_hit_riders(source, weapon, thrown=False):
    check = getattr(source, 'class_feature', None)
    if not callable(check):
        return []
    riders, groups = [], set()
    for feature, rider in FEATURE_HIT_RIDERS.items():
        if rider.get('group') in groups:
            continue
        if rider.get('melee_only') and not _is_melee_weapon_attack(weapon, thrown):
            continue
        try:
            if not check(feature):
                continue
        except Exception:
            continue
        groups.add(rider.get('group'))
        riders.append({k: v for k, v in rider.items() if k not in ('group', 'melee_only')})
    return riders
