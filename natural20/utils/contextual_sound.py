"""Short on-map sound cues rendered as contextual toasts near the source."""

from __future__ import annotations

from typing import Any, Dict, Optional


DEFAULT_CONTEXTUAL_SOUND_MS = 4000


def _position_for_anchor(anchor, position=None):
    if position is not None:
        return position
    if anchor is None:
        return None
    map_obj = getattr(anchor, 'map', None)
    if map_obj is None:
        return None
    try:
        return map_obj.position_of(anchor)
    except Exception:
        return None


def build_contextual_sound(
    source,
    message: str,
    position=None,
    *,
    duration_ms: int = DEFAULT_CONTEXTUAL_SOUND_MS,
    label: Optional[str] = None,
    sound_id: Optional[str] = None,
    anchor=None,
) -> Dict[str, Any]:
    """Build an action-result payload for a short map toast near a sound source."""
    resolved_position = _position_for_anchor(anchor or source, position)
    payload: Dict[str, Any] = {
        'type': 'contextual_sound',
        'source': source,
        'message': str(message),
        'position': resolved_position,
        'duration_ms': int(duration_ms or DEFAULT_CONTEXTUAL_SOUND_MS),
    }
    if label:
        payload['label'] = str(label)
    if sound_id:
        payload['sound_id'] = str(sound_id)
    return payload
