"""Creature-centered auras for VTT rendering (2D rings / 3D token discs).

A generic render channel: anything that projects a visible aura centred on a
creature shows up on its token in both VTT views. Two sources feed it:

- **Emanation zones** — ``PersistentAoEZone`` subclasses with
  ``shape == 'emanation'`` and a ``radius_ft`` (Spirit Guardians, Investiture
  of Flame). They are found on ``battle.active_zones`` or
  ``map.environment_zones`` and keyed by their ``owner``.
- **Support auras** — the YAML/class-feature auras of
  ``natural20/utils/auras.py`` (Paladin Aura of Protection and friends),
  which are always projected while the owner is conscious.

``JsonRenderer`` puts the list on the entity tile as ``creature_auras``;
``natural20/web/map_state.py`` forwards it into the 3D entity payload. The
web layer styles each entry by ``name`` (CSS class / fixture kind) and sizes
it by ``radius_tiles``.
"""
from __future__ import annotations

import math


def creature_auras(entity, battle=None, battle_map=None, feet_per_grid=5):
    """Visible auras centred on ``entity`` as render payloads.

    Each entry: ``{'name': str, 'radius_ft': int, 'radius_tiles': int}``.
    """
    auras = []
    seen = set()
    feet_per_grid = float(feet_per_grid or 5) or 5.0

    zones = []
    if battle is not None:
        zones.extend(getattr(battle, 'active_zones', None) or [])
    if battle_map is not None:
        zones.extend(getattr(battle_map, 'environment_zones', None) or [])
    for zone in zones:
        if getattr(zone, 'shape', None) != 'emanation':
            continue
        owner = getattr(zone, 'owner', None) or getattr(zone, 'source', None)
        if owner is not entity:
            continue
        name = str(getattr(zone, 'name', '') or '')
        try:
            radius_ft = float(getattr(zone, 'radius_ft', 0) or 0)
        except (TypeError, ValueError):
            radius_ft = 0.0
        if not name or radius_ft <= 0:
            continue
        _add(auras, seen, name, radius_ft, feet_per_grid)

    # Support auras (paladin auras, YAML `auras:`) are not zones; include the
    # ones this creature actively projects.
    try:
        from natural20.utils.auras import active_auras_of
        for aura in active_auras_of(entity) or []:
            name = str(aura.get('name') or '')
            try:
                radius_ft = float(aura.get('range') or 0)
            except (TypeError, ValueError):
                radius_ft = 0.0
            if not name or radius_ft <= 0:
                continue
            _add(auras, seen, name, radius_ft, feet_per_grid)
    except Exception:
        pass

    return auras


def _add(auras, seen, name, radius_ft, feet_per_grid):
    key = (name, radius_ft)
    if key in seen:
        return
    seen.add(key)
    auras.append({
        'name': name,
        'radius_ft': int(radius_ft),
        'radius_tiles': max(1, math.ceil(radius_ft / feet_per_grid)),
    })
