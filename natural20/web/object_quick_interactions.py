"""Compact hover interact buttons for doors and chests (VTT quick actions)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from natural20.item_library.chest import Chest
from natural20.item_library.door_object import DoorObject, DoorObjectWall

_QUICK_ACTION_ICONS = {
    'open': 'folder-open',
    'close': 'remove',
    'unlock': 'log-in',
    'lock': 'lock',
}

_QUICK_ACTION_IMAGE_SLUGS = {
    'open': 'interact_open',
    'close': 'interact_close',
    'unlock': 'interact_unlock',
    'lock': 'interact_lock',
}

_CHEST_ACTION_IMAGE_SLUGS = {
    'open': 'open_chest',
    'close': 'closed_chest',
    'unlock': 'interact_unlock',
    'lock': 'interact_lock',
}

_DOOR_FACING_FALLBACK_ANCHOR = {
    'up': 'bottom',
    'down': 'top',
    'left': 'right',
    'right': 'left',
}

_QUICK_ACTION_LABELS = {
    'open': 'Open',
    'close': 'Close',
    'unlock': 'Unlock',
    'lock': 'Lock',
}


def _action_image_slug(action: str, *, chest: bool = False) -> str:
    mapping = _CHEST_ACTION_IMAGE_SLUGS if chest else _QUICK_ACTION_IMAGE_SLUGS
    return mapping[action]


def door_quick_interact_anchor(door, pov_entity=None) -> str | None:
    """Place hover controls on the tile edge that faces the POV character."""
    door_map = getattr(door, 'map', None)
    if door_map is None:
        return None
    try:
        dx, dy = door_map.position_of(door)
    except (ValueError, KeyError, TypeError):
        dx = dy = None

    if pov_entity is not None and dx is not None and _entity_on_map(door_map, pov_entity):
        try:
            px, py = door_map.position_of(pov_entity)
        except (ValueError, KeyError, TypeError):
            px = py = None
        if px is not None and py is not None and (px, py) != (dx, dy):
            diff_x = px - dx
            diff_y = py - dy
            if abs(diff_x) > abs(diff_y):
                return 'right' if diff_x > 0 else 'left'
            return 'bottom' if diff_y > 0 else 'top'

    facing = getattr(door, 'facing', None)
    if callable(facing):
        return _DOOR_FACING_FALLBACK_ANCHOR.get(facing())
    return None


def _action_entry(
    action: str,
    interactions: Dict[str, Any],
    *,
    allow_approach: bool = True,
    chest: bool = False,
) -> Optional[Dict[str, Any]]:
    image = _action_image_slug(action, chest=chest)
    details = interactions.get(action)
    if details is None:
        if not allow_approach:
            return None
        return {
            'action': action,
            'label': _QUICK_ACTION_LABELS[action],
            'icon': _QUICK_ACTION_ICONS[action],
            'image': image,
            'disabled': False,
            'needs_approach': True,
        }
    if details.get('disabled'):
        return {
            'action': action,
            'label': _QUICK_ACTION_LABELS[action],
            'icon': _QUICK_ACTION_ICONS[action],
            'image': image,
            'disabled': True,
            'needs_approach': False,
            'disabled_text': details.get('disabled_text'),
        }
    return {
        'action': action,
        'label': _QUICK_ACTION_LABELS[action],
        'icon': _QUICK_ACTION_ICONS[action],
        'image': image,
        'disabled': False,
        'needs_approach': False,
    }


def _entity_on_map(map_obj, entity) -> bool:
    if not map_obj or not entity:
        return False
    if entity in map_obj.entities:
        return True
    uid = getattr(entity, 'entity_uid', None)
    if not uid:
        return False
    try:
        resolved = map_obj.entity_by_uid(uid)
    except Exception:
        return False
    return resolved is not None and resolved in map_obj.entities


def _door_quick_actions(door, pov_entity, battle=None, admin: bool = False) -> List[Dict[str, Any]]:
    if door.dead() or door.concealed():
        return []
    if not admin and not _entity_on_map(getattr(door, 'map', None), pov_entity):
        return []
    interactions = door.available_interactions(pov_entity, battle, admin=admin) or {}
    actions: List[Dict[str, Any]] = []

    if door.locked:
        entry = _action_entry('unlock', interactions)
        if entry:
            actions.append(entry)
    elif door.closed():
        entry = _action_entry('open', interactions)
        if entry:
            actions.append(entry)
    else:
        entry = _action_entry('close', interactions)
        if entry:
            actions.append(entry)

    if door.lockable and not door.locked:
        entry = _action_entry('lock', interactions)
        if entry:
            actions.append(entry)

    return actions


def _chest_quick_actions(chest: Chest, pov_entity, battle=None, admin: bool = False) -> List[Dict[str, Any]]:
    if chest.dead() or chest.concealed():
        return []
    interactions = chest.available_interactions(pov_entity, battle, admin=admin) or {}
    actions: List[Dict[str, Any]] = []

    if chest.locked():
        entry = _action_entry('unlock', interactions, chest=True)
        if entry:
            actions.append(entry)
    elif not chest.opened():
        entry = _action_entry('open', interactions, chest=True)
        if entry:
            actions.append(entry)
    else:
        entry = _action_entry('close', interactions, chest=True)
        if entry:
            actions.append(entry)

    if chest.lockable and not chest.locked():
        entry = _action_entry('lock', interactions, chest=True)
        if entry:
            actions.append(entry)

    return actions


def quick_interact_actions_for(object_entity, pov_entity, battle=None, admin: bool = False) -> List[Dict[str, Any]]:
    """Return quick-action metadata for doors/chests when a POV entity is selected."""
    if pov_entity is None or object_entity is None:
        return []
    if isinstance(object_entity, (DoorObject, DoorObjectWall)):
        return _door_quick_actions(object_entity, pov_entity, battle, admin=admin)
    if isinstance(object_entity, Chest):
        return _chest_quick_actions(object_entity, pov_entity, battle, admin=admin)
    return []
