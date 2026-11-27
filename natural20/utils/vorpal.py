"""Vorpal weapon beheading (2024 DMG ``Vorpal`` weapons, e.g. Vorpal Greatsword).

A weapon whose YAML definition sets ``vorpal: true`` removes a creature's
head on a natural 20. Creatures that can't lose a head to this weapon —
slashing-immune, headless types (construct, ooze, plant, swarm) or Huge and
larger — instead take an extra 30 slashing damage.

The instant death is modelled as a massive damage roll (remaining HP + 999)
so normal death handling, massive-damage checks and death attribution all
keep working.
"""
from __future__ import annotations

from natural20.die_roll import DieRoll

HEADLESS_TYPES = {'construct', 'ooze', 'plant', 'swarm'}
BIG_SIZES = {'huge', 'gargantuan'}


def _types(entity):
    found = set()
    try:
        from natural20.spell.condition_spells import _creature_types
        found |= {str(t).lower() for t in (_creature_types(entity) or [])}
    except Exception:
        pass
    race = getattr(entity, 'race', None)
    if callable(race):
        try:
            race = race()
        except Exception:
            race = None
    if isinstance(race, (list, tuple, set)):
        found |= {str(r).lower() for r in race}
    return found


def _extra_slashing(source, target, battle, why):
    roll = DieRoll.roll('30', battle=battle, entity=source,
                        description=f'dice_roll.vorpal_extra_slashing ({why})')
    return roll


def vorpal_beheading_roll(source, target, weapon, battle):
    """Damage roll added on a vorpal crit, or None when nothing applies."""
    if target is None or target.dead():
        return None
    if getattr(target, 'immune_to', lambda _t, **_kw: False)('slashing', source=source,
                                                             weapon=weapon):
        return _extra_slashing(source, target, battle, 'slashing immunity')
    if _types(target) & HEADLESS_TYPES:
        return _extra_slashing(source, target, battle, 'no head')
    size = getattr(target, 'size', None)
    if callable(size):
        try:
            size = size()
        except Exception:
            size = None
    if str(size or '').lower() in BIG_SIZES:
        return _extra_slashing(source, target, battle, 'too big to behead')
    remaining = max(1, int(getattr(target, 'hp', lambda: 1)() or 1))
    return DieRoll.roll(str(remaining + 999), battle=battle, entity=source,
                        description='dice_roll.vorpal_beheading')
