"""Inventory items that become interactable map objects when set down (e.g. a chest).

An item opts in with YAML ``placeable_object: <object type>``. Dropping it on the
ground places that object (carrying the item's container contents as the object's
inventory) and tags the object with ``portable_item: <item key>``. Any map object
with ``portable_item`` offers a ``pick_up`` interaction that folds it, contents and
all, back into the carrier's inventory if they can carry the combined weight.
"""

from __future__ import annotations

from typing import Any, Optional

from natural20.concern.inventory import serialize_inventory_for_yaml


def _item_definition(session, item_name) -> dict:
    if session is None or not item_name:
        return {}
    try:
        return session.load_thing(item_name) or {}
    except Exception:
        return {}


def placeable_object_type(session, item_name) -> Optional[str]:
    return _item_definition(session, item_name).get('placeable_object')


def portable_item_of(obj) -> Optional[str]:
    props = getattr(obj, 'properties', None) or {}
    return props.get('portable_item')


def _label(thing) -> str:
    label_fn = getattr(thing, 'label', None)
    if callable(label_fn):
        try:
            return str(label_fn())
        except Exception:
            pass
    return str(getattr(thing, 'name', thing))


def _message(session, source, target, message):
    if session is None or not getattr(session, 'event_manager', None):
        return
    session.event_manager.received_event({
        'event': 'message',
        'source': source,
        'target': target,
        'message': message,
    })


def place_object_from_item(session, item_name, entry: Any, map_obj, origin, source=None):
    """Put the object for *item_name* on *map_obj* at *origin*. Returns ``(obj, reason)``."""
    object_type = placeable_object_type(session, item_name)
    if not object_type:
        return None, 'Item cannot be placed'
    if map_obj is None or origin is None:
        return None, 'No place to set it down'
    object_info = session.load_object(object_type) if session is not None else None
    if not object_info:
        return None, f'Unknown object: {object_type}'

    contents = []
    if isinstance(entry, dict):
        contents = [dict(row) for row in (entry.get('contents') or []) if isinstance(row, dict)]
    object_meta = {
        'portable_item': item_name,
        'inventory': contents,
    }
    obj = map_obj.place_object(object_info, int(origin[0]), int(origin[1]), object_meta=object_meta)
    if obj is None:
        return None, 'Could not place the object'
    if source is not None:
        _message(session, source, obj, f"{_label(source)} sets down {_label(obj)}.")
    return obj, None


def portable_object_weight_lbs(carrier, obj, session=None) -> float:
    """Item weight plus everything stored inside the object."""
    item_name = portable_item_of(obj)
    session = session or getattr(carrier, 'session', None) or getattr(obj, 'session', None)
    try:
        total = float(_item_definition(session, item_name).get('weight') or 0)
    except (TypeError, ValueError):
        total = 0.0
    weight_fn = getattr(obj, 'inventory_weight', None)
    if callable(weight_fn):
        try:
            total += float(weight_fn(session) or 0)
        except Exception:
            pass
    return total


def can_pickup_object(carrier, obj, session=None):
    item_name = portable_item_of(obj)
    if carrier is None or obj is None or not item_name:
        return False, 'Cannot pick that up'
    session = session or getattr(carrier, 'session', None) or getattr(obj, 'session', None)
    accept = getattr(carrier, 'can_accept_item', None)
    if callable(accept):
        check = {'type': item_name, 'qty': 1, 'weight': portable_object_weight_lbs(carrier, obj, session)}
        ok, reason = accept(item_name, 1, source_item=check, session=session)
        if not ok:
            return False, reason
    return True, None


def pickup_object(carrier, obj, battle=None, session=None):
    """Remove *obj* from its map and add its item (with contents) to *carrier*."""
    session = session or getattr(carrier, 'session', None) or getattr(obj, 'session', None)
    ok, reason = can_pickup_object(carrier, obj, session=session)
    if not ok:
        _message(session, carrier, obj, reason or 'Cannot pick that up.')
        return False, reason

    item_name = portable_item_of(obj)
    entry = {
        'type': item_name,
        'qty': 1,
        'contents': serialize_inventory_for_yaml(getattr(obj, 'inventory', None)) or [],
        'is_container': True,
    }
    map_obj = getattr(obj, 'map', None)
    if map_obj is None and session is not None:
        map_obj = session.map_for(obj)
    if map_obj is not None:
        map_obj.remove(obj, battle=battle)
    carrier.add_item(item_name, 1, source_item=entry)
    _message(session, carrier, obj, f"{_label(carrier)} picks up {_label(obj)}.")
    return True, None
