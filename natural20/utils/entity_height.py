"""Resolve creature standing and eye height for 3D line of sight."""

from __future__ import annotations

from typing import Any, Optional

# Typical standing height by size category (feet), PHB/SRD averages.
DEFAULT_STANDING_HEIGHT_FT: dict[str, float] = {
    'tiny': 2.5,
    'small': 3.5,
    'medium': 5.75,
    'large': 10.0,
    'huge': 20.0,
    'gargantuan': 35.0,
}

# Eye level as a fraction of standing height when not explicitly set.
_EYE_HEIGHT_RATIO = 0.92

# Prone eye height above the floor (feet).
_PRONE_EYE_HEIGHT_FT = 1.0


def entity_size_category(entity: Any) -> str:
    if hasattr(entity, 'size') and callable(entity.size):
        try:
            size = entity.size()
            if size:
                return str(size).lower()
        except Exception:
            pass
    props = getattr(entity, 'properties', None) or {}
    if props.get('size'):
        return str(props['size']).lower()
    race_props = getattr(entity, 'race_properties', None) or {}
    if race_props.get('size'):
        return str(race_props['size']).lower()
    return 'medium'


def _race_height_overrides(entity: Any) -> tuple[Optional[float], Optional[float]]:
    """Return (standing_ft, eye_ft) from race/subrace YAML if present."""
    race_props = getattr(entity, 'race_properties', None) or {}
    if not race_props:
        return None, None
    subrace_key = None
    if hasattr(entity, 'subrace') and callable(entity.subrace):
        try:
            subrace_key = entity.subrace()
        except Exception:
            subrace_key = None
    sub = {}
    if subrace_key:
        sub = (race_props.get('subrace') or {}).get(subrace_key, {}) or {}
    standing = (
        sub.get('average_height_ft')
        or sub.get('height_ft')
        or race_props.get('average_height_ft')
        or race_props.get('height_ft')
    )
    eye = (
        sub.get('eye_height_ft')
        or sub.get('sight_height_ft')
        or race_props.get('eye_height_ft')
        or race_props.get('sight_height_ft')
    )
    return (
        float(standing) if standing is not None else None,
        float(eye) if eye is not None else None,
    )


def _wild_shape_beast_props(entity: Any) -> dict:
    state = getattr(entity, '_wild_shape_state', None)
    if not state:
        return {}
    return state.get('beast_props', {}) or {}


def standing_height_ft(entity: Any) -> float:
    props = getattr(entity, 'properties', None) or {}
    if props.get('height_ft') is not None:
        return float(props['height_ft'])
    if props.get('standing_height_ft') is not None:
        return float(props['standing_height_ft'])
    race_standing, _ = _race_height_overrides(entity)
    if race_standing is not None:
        return race_standing
    beast = _wild_shape_beast_props(entity)
    if beast.get('height_ft') is not None:
        return float(beast['height_ft'])
    if beast.get('size'):
        return DEFAULT_STANDING_HEIGHT_FT.get(str(beast['size']).lower(), 5.75)
    size = entity_size_category(entity)
    return DEFAULT_STANDING_HEIGHT_FT.get(size, 5.75)


def eye_height_ft(entity: Any) -> float:
    props = getattr(entity, 'properties', None) or {}
    if props.get('eye_height_ft') is not None:
        return float(props['eye_height_ft'])
    if props.get('sight_height_ft') is not None:
        return float(props['sight_height_ft'])
    _, race_eye = _race_height_overrides(entity)
    if race_eye is not None:
        return race_eye
    if hasattr(entity, 'prone') and callable(entity.prone):
        try:
            if entity.prone():
                return _PRONE_EYE_HEIGHT_FT
        except Exception:
            pass
    return standing_height_ft(entity) * _EYE_HEIGHT_RATIO
