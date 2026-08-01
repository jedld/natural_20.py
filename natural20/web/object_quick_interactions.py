"""Compact hover interact buttons for map objects (doors, chests, switches, etc.)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set

from natural20.concern.lootable import Lootable
from natural20.item_library.chest import Chest
from natural20.item_library.door_object import DoorObject, DoorObjectWall
from natural20.item_library.object import Object
from natural20.web.quick_interact_registry import (
    glyph_icon_for_action,
    resolve_action_image_slug,
    resolve_action_label,
)

_QUICK_ACTION_ICONS = {
    'open': 'folder-open',
    'close': 'remove',
    'unlock': 'log-in',
    'lock': 'lock',
    'loot': 'briefcase',
}

_QUICK_ACTION_IMAGE_SLUGS = {
    'open': 'interact_open',
    'close': 'interact_close',
    'unlock': 'interact_unlock',
    'lock': 'interact_lock',
    'loot': 'interact_loot',
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

_DOOR_FACING_OFFSETS = {
    'up': (0, -1),
    'down': (0, 1),
    'left': (-1, 0),
    'right': (1, 0),
}

_DOOR_OFFSET_TO_ANCHOR = {
    (0, -1): 'top',
    (0, 1): 'bottom',
    (-1, 0): 'left',
    (1, 0): 'right',
}

_ANCHOR_APPROACH_OFFSET = {v: k for k, v in _DOOR_OFFSET_TO_ANCHOR.items()}

_QUICK_ACTION_LABELS = {
    'open': 'Open',
    'close': 'Close',
    'unlock': 'Unlock',
    'lock': 'Lock',
    'loot': 'Loot',
}

# Door/chest state actions are rendered by specialized builders; everything else is generic.
_STRUCTURED_OBJECT_ACTIONS: Set[str] = {'open', 'close', 'unlock', 'lock', 'loot'}


def _target_label(target) -> str:
    label_fn = getattr(target, 'label', None)
    if callable(label_fn):
        return str(label_fn())
    return str(getattr(target, 'name', 'target'))


def _loot_action_label(target) -> str:
    return f"Loot {_target_label(target)}"


def _shares_tile_with_pov(map_obj, target, pov_entity) -> bool:
    """True when *target* occupies the same map square as the POV character."""
    if not map_obj or not target or not pov_entity:
        return False
    try:
        return map_obj.position_of(target) == map_obj.position_of(pov_entity)
    except (ValueError, KeyError, TypeError):
        return False


def _in_interact_range(pov_entity, target, battle, map_obj) -> bool:
    if not map_obj or not pov_entity or target is None:
        return False
    try:
        if target in map_obj.objects_near(pov_entity, battle):
            return True
    except Exception:
        pass
    try:
        tx, ty = map_obj.position_of(target)
        px, py = map_obj.position_of(pov_entity)
    except (ValueError, KeyError, TypeError):
        return False
    if (px, py) == (tx, ty):
        return True
    for square in pov_entity.melee_squares(map_obj):
        if square[0] == tx and square[1] == ty:
            return True
    return False


def _loot_action_entry(
    target,
    pov_entity,
    battle,
    map_obj,
    *,
    admin: bool = False,
) -> Optional[Dict[str, Any]]:
    interactions = target.available_interactions(pov_entity, battle, admin=admin) or {}
    if 'loot' not in interactions:
        return None

    label = _loot_action_label(target)
    details = interactions.get('loot') or {}
    in_range = admin or _in_interact_range(pov_entity, target, battle, map_obj)

    if not in_range:
        return {
            'action': 'loot',
            'label': label,
            'icon': _QUICK_ACTION_ICONS['loot'],
            'image': _QUICK_ACTION_IMAGE_SLUGS['loot'],
            'disabled': False,
            'needs_approach': True,
        }

    if details.get('disabled'):
        return {
            'action': 'loot',
            'label': label,
            'icon': _QUICK_ACTION_ICONS['loot'],
            'image': _QUICK_ACTION_IMAGE_SLUGS['loot'],
            'disabled': True,
            'needs_approach': False,
            'disabled_text': details.get('disabled_text'),
        }

    return {
        'action': 'loot',
        'label': label,
        'icon': _QUICK_ACTION_ICONS['loot'],
        'image': _QUICK_ACTION_IMAGE_SLUGS['loot'],
        'disabled': False,
        'needs_approach': False,
    }


def _action_image_slug(action: str, *, chest: bool = False) -> str:
    mapping = _CHEST_ACTION_IMAGE_SLUGS if chest else _QUICK_ACTION_IMAGE_SLUGS
    return mapping[action]


def _door_facing_name(door) -> str | None:
    facing = getattr(door, 'facing', None)
    if callable(facing):
        return facing()
    return None


def door_open_approach_anchors(door) -> List[str]:
    """Return CSS anchor names for squares from which the door may be opened."""
    facing = _door_facing_name(door)
    if not facing:
        return []
    front = _DOOR_FACING_OFFSETS.get(facing)
    back = _DOOR_FACING_OFFSETS.get(
        {'up': 'down', 'down': 'up', 'left': 'right', 'right': 'left'}.get(facing, ''),
    )
    anchors: List[str] = []
    for offset in (front, back):
        if offset and offset in _DOOR_OFFSET_TO_ANCHOR:
            anchor = _DOOR_OFFSET_TO_ANCHOR[offset]
            if anchor not in anchors:
                anchors.append(anchor)
    return anchors


def _approach_square_for_anchor(door_x: int, door_y: int, anchor: str) -> tuple[int, int]:
    offset = _ANCHOR_APPROACH_OFFSET.get(anchor, (0, 0))
    return door_x + offset[0], door_y + offset[1]


def _anchor_toward_point(from_x: int, from_y: int, to_x: int, to_y: int) -> str:
    diff_x = to_x - from_x
    diff_y = to_y - from_y
    if abs(diff_x) > abs(diff_y):
        return 'right' if diff_x > 0 else 'left'
    return 'bottom' if diff_y > 0 else 'top'


def _pick_visible_approach_anchor(
    door_x: int,
    door_y: int,
    valid_anchors: List[str],
    approach_tile_visible: Callable[[int, int], bool] | None,
) -> List[str]:
    if not approach_tile_visible or not valid_anchors:
        return valid_anchors
    visible = [
        anchor
        for anchor in valid_anchors
        if approach_tile_visible(*_approach_square_for_anchor(door_x, door_y, anchor))
    ]
    return visible or valid_anchors


def door_quick_interact_anchor(
    door,
    pov_entity=None,
    *,
    approach_tile_visible: Callable[[int, int], bool] | None = None,
) -> str | None:
    """Place hover controls on a valid, preferably visible, approach edge."""
    door_map = getattr(door, 'map', None)
    if door_map is None:
        return None
    try:
        dx, dy = door_map.position_of(door)
    except (ValueError, KeyError, TypeError):
        return None

    valid_anchors = door_open_approach_anchors(door)
    if not valid_anchors:
        facing = _door_facing_name(door)
        return _DOOR_FACING_FALLBACK_ANCHOR.get(facing) if facing else None

    px = py = None
    if pov_entity is not None and _entity_on_map(door_map, pov_entity):
        try:
            px, py = door_map.position_of(pov_entity)
        except (ValueError, KeyError, TypeError):
            px = py = None

    if px is not None and py is not None:
        for anchor in valid_anchors:
            ax, ay = _approach_square_for_anchor(dx, dy, anchor)
            if (px, py) == (ax, ay):
                return anchor

        if (px, py) != (dx, dy):
            toward_pov = _anchor_toward_point(dx, dy, px, py)
            visible_valid = _pick_visible_approach_anchor(
                dx, dy, valid_anchors, approach_tile_visible,
            )
            if toward_pov in visible_valid:
                return toward_pov
            return visible_valid[0]

    visible_valid = _pick_visible_approach_anchor(
        dx, dy, valid_anchors, approach_tile_visible,
    )
    facing = _door_facing_name(door)
    fallback = _DOOR_FACING_FALLBACK_ANCHOR.get(facing) if facing else None
    if fallback and fallback in visible_valid:
        return fallback
    return visible_valid[0]


def _action_entry(
    action: str,
    interactions: Dict[str, Any],
    *,
    allow_approach: bool = True,
    chest: bool = False,
    object_entity=None,
) -> Optional[Dict[str, Any]]:
    image = _action_image_slug(action, chest=chest)
    if object_entity is not None:
        image = resolve_action_image_slug(object_entity, action) or image
    label = _QUICK_ACTION_LABELS.get(action)
    if object_entity is not None:
        label = resolve_action_label(object_entity, action, interactions.get(action))
    elif not label:
        label = action.replace('_', ' ').title()
    icon = _QUICK_ACTION_ICONS.get(action) or glyph_icon_for_action(action)
    details = interactions.get(action)
    show_label = image is None
    if details is None:
        if not allow_approach:
            return None
        return {
            'action': action,
            'label': label,
            'icon': icon,
            'image': image,
            'show_label': show_label,
            'disabled': False,
            'needs_approach': True,
        }
    if details.get('disabled'):
        return {
            'action': action,
            'label': label,
            'icon': icon,
            'image': image,
            'show_label': show_label,
            'disabled': True,
            'needs_approach': False,
            'disabled_text': details.get('disabled_text'),
        }
    return {
        'action': action,
        'label': label,
        'icon': icon,
        'image': image,
        'show_label': show_label,
        'disabled': False,
        'needs_approach': False,
    }


def _generic_interaction_entry(
    action: str,
    details: Any,
    object_entity,
    pov_entity,
    battle,
    map_obj,
    *,
    admin: bool = False,
) -> Optional[Dict[str, Any]]:
    if not action:
        return None
    if isinstance(details, str):
        details = {'prompt': details}
    if not isinstance(details, dict):
        details = {}

    image = resolve_action_image_slug(object_entity, action)
    label = resolve_action_label(object_entity, action, details)
    icon = glyph_icon_for_action(action)
    show_label = image is None
    in_range = admin or _in_interact_range(pov_entity, object_entity, battle, map_obj)

    if not in_range and not details:
        return {
            'action': action,
            'label': label,
            'icon': icon,
            'image': image,
            'show_label': show_label,
            'disabled': False,
            'needs_approach': True,
        }

    if details.get('disabled'):
        return {
            'action': action,
            'label': label,
            'icon': icon,
            'image': image,
            'show_label': show_label,
            'disabled': True,
            'needs_approach': False,
            'disabled_text': details.get('disabled_text'),
        }

    if not in_range:
        return {
            'action': action,
            'label': label,
            'icon': icon,
            'image': image,
            'show_label': show_label,
            'disabled': False,
            'needs_approach': True,
        }

    return {
        'action': action,
        'label': label,
        'icon': icon,
        'image': image,
        'show_label': show_label,
        'disabled': False,
        'needs_approach': False,
    }


def quick_interact_layout_for(actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Suggest hover layout based on how many actions and whether they use text labels."""
    count = len(actions)
    if count <= 1:
        return {'count': count, 'columns': 1}
    labeled = sum(1 for action in actions if action.get('show_label'))
    columns = 2 if count >= 3 or labeled >= 2 else 1
    return {'count': count, 'columns': columns}


def object_quick_interact_anchor(object_entity, pov_entity=None) -> str | None:
    """Place generic object controls on the edge nearest the POV character."""
    object_map = getattr(object_entity, 'map', None)
    if object_map is None:
        return None
    try:
        ox, oy = object_map.position_of(object_entity)
    except (ValueError, KeyError, TypeError):
        return None
    if pov_entity is None or not _entity_on_map(object_map, pov_entity):
        return 'top'
    try:
        px, py = object_map.position_of(pov_entity)
    except (ValueError, KeyError, TypeError):
        return 'top'
    if (px, py) == (ox, oy):
        return 'top'
    return _anchor_toward_point(ox, oy, px, py)


def _supplemental_quick_actions(
    object_entity,
    pov_entity,
    battle=None,
    existing_actions: Optional[List[Dict[str, Any]]] = None,
    *,
    admin: bool = False,
    skip_actions: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Build quick actions from ``available_interactions`` not already covered."""
    if object_entity is None or pov_entity is None:
        return []
    if object_entity.dead() or object_entity.concealed():
        return []
    map_obj = getattr(object_entity, 'map', None)
    if not admin and map_obj is not None and not _entity_on_map(map_obj, pov_entity):
        return []

    interactions = object_entity.available_interactions(pov_entity, battle, admin=admin) or {}
    if not interactions:
        return []

    covered = {entry['action'] for entry in (existing_actions or [])}
    blocked = set(skip_actions or set())
    actions: List[Dict[str, Any]] = []

    for action, details in interactions.items():
        if action in covered or action in blocked:
            continue
        entry = _generic_interaction_entry(
            action,
            details,
            object_entity,
            pov_entity,
            battle,
            map_obj,
            admin=admin,
        )
        if entry:
            actions.append(entry)

    actions.sort(key=lambda item: (item.get('disabled', False), str(item.get('label', ''))))
    return actions


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
    map_obj = getattr(chest, 'map', None)

    if chest.locked():
        entry = _action_entry('unlock', interactions, chest=True)
        if entry:
            actions.append(entry)
    elif not chest.opened():
        entry = _action_entry('open', interactions, chest=True)
        if entry:
            actions.append(entry)
    else:
        loot_entry = _loot_action_entry(chest, pov_entity, battle, map_obj, admin=admin)
        if loot_entry:
            actions.append(loot_entry)
        entry = _action_entry('close', interactions, chest=True)
        if entry:
            actions.append(entry)

    if chest.lockable and not chest.locked():
        entry = _action_entry('lock', interactions, chest=True)
        if entry:
            actions.append(entry)

    return actions


def _object_loot_quick_actions(obj: Object, pov_entity, battle=None, admin: bool = False) -> List[Dict[str, Any]]:
    if obj.dead() or obj.concealed():
        return []
    inventory = getattr(obj, 'inventory', None) or {}
    if not inventory:
        return []
    map_obj = getattr(obj, 'map', None)
    entry = _loot_action_entry(obj, pov_entity, battle, map_obj, admin=admin)
    return [entry] if entry else []


def _perception_capable(entity) -> bool:
    return callable(getattr(entity, 'perception_check', None))


def pov_self_quick_interact_anchor(map_obj, entity) -> str | None:
    """Place the POV perception button toward the map interior for visibility."""
    if map_obj is None or entity is None:
        return None
    try:
        _x, y = map_obj.position_of(entity)
        _w, height = map_obj.size
    except (ValueError, KeyError, TypeError):
        return 'top'
    if height <= 1:
        return 'bottom'
    return 'bottom' if y < (height / 2) else 'top'


def pov_self_quick_interact_actions_for(
    entity,
    battle=None,
    map_obj=None,
) -> List[Dict[str, Any]]:
    """Hover quick action for the POV character to roll Perception on their own token."""
    if entity is None or not _perception_capable(entity):
        return []
    if map_obj is not None and not _entity_on_map(map_obj, entity):
        return []

    return [{
        'action': 'perception_check',
        'kind': 'pov_perception',
        'label': 'action.look',
        'image': 'look',
        'show_label': False,
        'disabled': False,
    }]


def entity_quick_interact_actions_for(
    entity,
    pov_entity,
    battle=None,
    map_obj=None,
    admin: bool = False,
) -> List[Dict[str, Any]]:
    """Return loot quick-action metadata for dead/unconscious lootable entities."""
    if entity is None or pov_entity is None:
        return []
    if getattr(entity, 'entity_uid', None) == getattr(pov_entity, 'entity_uid', None):
        return []
    if not isinstance(entity, Lootable):
        return []
    if not (entity.dead() or entity.unconscious()):
        return []
    if not admin and map_obj is not None and not _entity_on_map(map_obj, pov_entity):
        return []

    entry = _loot_action_entry(entity, pov_entity, battle, map_obj, admin=admin)
    return [entry] if entry else []


def quick_interact_actions_for(object_entity, pov_entity, battle=None, admin: bool = False) -> List[Dict[str, Any]]:
    """Return hover quick-action metadata for any interactable map object."""
    if pov_entity is None or object_entity is None:
        return []

    map_obj = getattr(object_entity, 'map', None)
    if not admin and map_obj is not None and _shares_tile_with_pov(map_obj, object_entity, pov_entity):
        return []

    actions: List[Dict[str, Any]] = []
    skip_generic: Set[str] = set()

    if isinstance(object_entity, (DoorObject, DoorObjectWall)):
        actions = _door_quick_actions(object_entity, pov_entity, battle, admin=admin)
        skip_generic = set(_STRUCTURED_OBJECT_ACTIONS)
    elif isinstance(object_entity, Chest):
        actions = _chest_quick_actions(object_entity, pov_entity, battle, admin=admin)
        skip_generic = set(_STRUCTURED_OBJECT_ACTIONS)
    elif isinstance(object_entity, Object):
        actions = _object_loot_quick_actions(object_entity, pov_entity, battle, admin=admin)
        skip_generic = {'loot'}

    supplemental = _supplemental_quick_actions(
        object_entity,
        pov_entity,
        battle,
        actions,
        admin=admin,
        skip_actions=skip_generic,
    )
    if supplemental:
        actions = actions + supplemental

    return actions
