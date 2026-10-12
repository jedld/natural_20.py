"""Death saving throw progress for map rendering (2D token overlay, 3D state)."""

from __future__ import annotations

from typing import Any, Dict

DEATH_SAVE_TARGET = 3


def death_save_info(entity) -> Dict[str, Any] | None:
    """Return save/fail tallies for a creature dying at 0 HP, else ``None``.

    Only creatures that roll death saves (PCs, in-party sidekicks) qualify;
    NPCs knocked out at 0 HP never roll, so they get no tracker.
    """
    try:
        if entity.dead() or not entity.unconscious():
            return None
        if not entity.makes_death_saves():
            return None
        if entity.hp() is None or entity.hp() > 0:
            return None
        stable = bool(entity.stable())
    except Exception:
        return None
    successes = max(0, min(DEATH_SAVE_TARGET, int(getattr(entity, 'death_saves', 0) or 0)))
    failures = max(0, min(DEATH_SAVE_TARGET, int(getattr(entity, 'death_fails', 0) or 0)))
    return {
        'successes': successes,
        'failures': failures,
        'stable': stable,
        'target': DEATH_SAVE_TARGET,
    }


def death_save_tooltip(info: Dict[str, Any]) -> str:
    if info.get('stable'):
        return 'Stable (unconscious at 0 HP)'
    return (
        f"Death saves: {info['successes']}/{info['target']} successes, "
        f"{info['failures']}/{info['target']} failures"
    )


def death_save_tile_attributes(entity) -> Dict[str, Any]:
    """Tile dict keys for a token tile; empty unless the creature is dying."""
    info = death_save_info(entity)
    if info is None:
        return {}
    return {
        'death_saves': info,
        'death_save_tooltip': death_save_tooltip(info),
    }
