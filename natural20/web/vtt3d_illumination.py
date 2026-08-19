"""Play-time 3D ambient illumination overrides.

YAML ``map.illumination`` stays the default. The DM can raise or lower the
Three.js hemisphere / directional / fill lights without changing
``Map.light_at``, fog, or LOS. Overrides live in
``session.session_state['vtt3d_illumination']`` (per map name) and persist
with save/load.
"""
from __future__ import annotations

from typing import Any

STATE_KEY = 'vtt3d_illumination'


def clamp_illumination(value, default: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if number != number:  # NaN
        number = default
    # DOM slider is 0–100; APIs use 0–1.
    if 2.0 <= number <= 100.0:
        number = number / 100.0
    return max(0.0, min(1.0, number))


def yaml_illumination(battle_map) -> float:
    props = getattr(battle_map, 'properties', None) or {}
    map_block = props.get('map') if isinstance(props.get('map'), dict) else {}
    return clamp_illumination(map_block.get('illumination', 1.0), 1.0)


def _store(session) -> dict[str, float]:
    if session is None:
        return {}
    state = getattr(session, 'session_state', None)
    if not isinstance(state, dict):
        session.session_state = {}
        state = session.session_state
    raw = state.get(STATE_KEY)
    if not isinstance(raw, dict):
        raw = {}
        state[STATE_KEY] = raw
    return raw


def map_key(battle_map) -> str | None:
    name = str(getattr(battle_map, 'name', None) or '').strip()
    return name or None


def get_override(session, name: str | None) -> float | None:
    if not name:
        return None
    store = _store(session)
    if name not in store:
        return None
    return clamp_illumination(store.get(name), 0.0)


def set_override(session, name: str, value: float | None) -> None:
    if not name:
        raise ValueError('map name is required')
    store = _store(session)
    if value is None:
        store.pop(name, None)
        return
    store[name] = clamp_illumination(value, 0.0)


def resolve_illumination(battle_map, session=None) -> dict[str, Any]:
    """Return effective 3D ambient plus the YAML default."""
    default = yaml_illumination(battle_map)
    name = map_key(battle_map)
    sess = session if session is not None else getattr(battle_map, 'session', None)
    override = get_override(sess, name)
    effective = default if override is None else override
    return {
        'map': name,
        'illumination': effective,
        'illumination_default': default,
        'illumination_overridden': override is not None,
    }


def apply_illumination(session, battle_map, value) -> dict[str, Any]:
    """Set, clear, or snap-to-default the 3D ambient for ``battle_map``.

    ``value`` of ``None`` clears the override (map YAML default). A value
    equal to the YAML default also clears the override.
    """
    name = map_key(battle_map)
    if not name:
        raise ValueError('map has no name')
    default = yaml_illumination(battle_map)
    if value is None:
        set_override(session, name, None)
    else:
        clamped = clamp_illumination(value, default)
        if abs(clamped - default) < 1e-6:
            set_override(session, name, None)
        else:
            set_override(session, name, clamped)
    return resolve_illumination(battle_map, session)
