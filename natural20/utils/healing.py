"""Shared healing-roll adjustments.

Effects that change how much a creature regains from *any* healing register
on the healed creature:

* ``max_healing`` — the creature regains the maximum possible hit points
  from dice-based healing (Beacon of Hope). The handler returns a truthy
  value while it applies.

Healing paths that roll dice (``spell_heal`` items, healing potions, potion
effect items, Aura of Vitality pulses) pass their roll through
``effective_heal_roll`` before reading ``result()``.
"""
from __future__ import annotations


def maximizes_healing(target) -> bool:
    if target is None or not hasattr(target, 'has_effect'):
        return False
    try:
        if not target.has_effect('max_healing'):
            return False
        return bool(target.eval_effect('max_healing', {'value': False}))
    except Exception:
        return False


def effective_heal_roll(target, roll):
    """``roll`` as ``target`` actually benefits from it (maximized under Beacon of Hope)."""
    if roll is None or not maximizes_healing(target):
        return roll
    maximized = getattr(roll, 'maximized', None)
    if not callable(maximized):
        return roll
    return maximized()
