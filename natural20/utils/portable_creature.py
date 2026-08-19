"""Pick up, store, and drop dead NPCs / player characters as inventory objects."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from natural20.utils.item_size import creature_body_weight_lbs, normalize_size

CREATURE_ITEM_PREFIX = 'creature:'
_SKIP = object()
_PRIMITIVES = (str, int, float, bool, bytes, type(None))


def creature_inventory_key(entity) -> str:
    uid = getattr(entity, 'entity_uid', None) or 'unknown'
    return f'{CREATURE_ITEM_PREFIX}{uid}'


def is_portable_creature_entry(entry: Any, item_name: Any = None) -> bool:
    if isinstance(item_name, str) and item_name.startswith(CREATURE_ITEM_PREFIX):
        return True
    if isinstance(entry, dict) and (entry.get('is_creature') or entry.get('payload')):
        type_name = str(entry.get('type') or entry.get('item') or '')
        if type_name.startswith(CREATURE_ITEM_PREFIX):
            return True
        if entry.get('is_creature'):
            return True
    return False


def is_dead_portable_creature(entity) -> bool:
    if entity is None:
        return False
    object_fn = getattr(entity, 'object', None)
    if callable(object_fn) and object_fn():
        return False
    dead_fn = getattr(entity, 'dead', None)
    if not callable(dead_fn) or not dead_fn():
        return False
    npc_fn = getattr(entity, 'npc', None)
    if callable(npc_fn) and npc_fn():
        return True
    # Player characters (and other non-object creatures).
    return True


def creature_carry_weight_lbs(entity, session=None) -> float:
    """Body weight plus carried/worn gear."""
    total = creature_body_weight_lbs(entity)
    weight_fn = getattr(entity, 'inventory_weight', None)
    if callable(weight_fn):
        try:
            total += float(weight_fn(session or getattr(entity, 'session', None)) or 0)
        except Exception:
            pass
    return total


def _creature_kind(entity) -> str:
    npc_fn = getattr(entity, 'npc', None)
    if callable(npc_fn) and npc_fn():
        return 'npc'
    return 'pc'


def _creature_label(entity) -> str:
    label_fn = getattr(entity, 'label', None)
    if callable(label_fn):
        try:
            name = str(label_fn())
        except Exception:
            name = str(getattr(entity, 'name', 'creature'))
    else:
        name = str(getattr(entity, 'name', 'creature') or 'creature')
    return f'{name} (dead)'


def _creature_size(entity) -> str:
    size_fn = getattr(entity, 'size', None)
    if callable(size_fn):
        try:
            return normalize_size(size_fn(), default='medium')
        except Exception:
            pass
    props = getattr(entity, 'properties', None) or {}
    return normalize_size(props.get('size'), default='medium')


def _yaml_safe_copy(value, memo=None):
    """Copy JSON/YAML-safe data; skip live objects (Session, locks, entities)."""
    if isinstance(value, _PRIMITIVES):
        return value
    if isinstance(value, (date, datetime, UUID)):
        return str(value) if isinstance(value, UUID) else value

    if memo is None:
        memo = {}
    obj_id = id(value)
    if obj_id in memo:
        return memo[obj_id]

    if isinstance(value, Mapping):
        out = {}
        memo[obj_id] = out
        try:
            items = list(value.items())
        except Exception:
            return _SKIP
        for key, item in items:
            if key == 'session' or not isinstance(key, (str, int, float, bool)):
                continue
            copied = _yaml_safe_copy(item, memo)
            if copied is _SKIP:
                continue
            out[key] = copied
        return out

    if isinstance(value, (list, tuple, set, frozenset)):
        out = []
        memo[obj_id] = out
        for item in value:
            copied = _yaml_safe_copy(item, memo)
            if copied is not _SKIP:
                out.append(copied)
        return out

    if isinstance(value, Sequence):
        out = []
        memo[obj_id] = out
        try:
            for item in value:
                copied = _yaml_safe_copy(item, memo)
                if copied is not _SKIP:
                    out.append(copied)
        except Exception:
            return _SKIP
        return out

    uid = getattr(value, 'entity_uid', None)
    if isinstance(uid, str) and uid:
        return uid
    return _SKIP


def _creature_item_stub(entity) -> dict:
    """Capacity-check shape for ``can_accept_item`` — no ``to_dict`` / deepcopy."""
    return {
        'type': creature_inventory_key(entity),
        'qty': 1,
        'is_creature': True,
        'entity_uid': getattr(entity, 'entity_uid', None),
        'size': _creature_size(entity),
        'weight': round(creature_carry_weight_lbs(entity, getattr(entity, 'session', None)), 2),
        'label': _creature_label(entity),
    }


def serialize_portable_creature(entity) -> dict:
    """YAML-safe snapshot stored on an inventory entry."""
    kind = _creature_kind(entity)
    raw = entity.to_dict() if hasattr(entity, 'to_dict') else {}
    try:
        payload = _yaml_safe_copy(raw) if isinstance(raw, Mapping) else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.pop('session', None)
    if kind == 'npc':
        payload.setdefault('npc_type', getattr(entity, 'npc_type', None))
        payload.setdefault('type', 'npc')
    else:
        payload.setdefault('type', 'pc')
    payload['entity_uid'] = getattr(entity, 'entity_uid', payload.get('entity_uid'))
    payload['name'] = getattr(entity, 'name', payload.get('name'))
    snapshot = _creature_item_stub(entity)
    snapshot['creature_kind'] = kind
    snapshot['image'] = 'interact_pickup_drop'
    snapshot['payload'] = payload
    return snapshot


def restore_portable_creature(session, entry: dict):
    """Rebuild a live entity from an inventory snapshot."""
    if not entry:
        return None
    uid = entry.get('entity_uid')
    if uid and session is not None:
        live = session.entity_by_uid(uid)
        if live is not None and is_dead_portable_creature(live):
            return live

    payload = copy.deepcopy(entry.get('payload') or {})
    if not payload:
        return None
    payload['session'] = session
    kind = entry.get('creature_kind') or payload.get('type') or payload.get('creature_kind')
    if kind == 'pc' or payload.get('type') == 'pc':
        from natural20.player_character import PlayerCharacter
        creature = PlayerCharacter.from_dict(payload)
    else:
        from natural20.npc import Npc
        creature = Npc.from_dict(payload)
    if session is not None:
        session.register_entity(creature)
        pin = getattr(session.entity_registry, 'pin', None)
        if callable(pin):
            pin(creature)
    return creature


def portable_creature_item_row(entry: dict, item_name=None) -> dict:
    """Shape used by ``inventory_items`` / loot UI."""
    key = item_name or entry.get('type')
    return {
        'name': key,
        'type': key,
        'label': entry.get('label') or 'Body',
        'qty': int(entry.get('qty', 1) or 1),
        'image': entry.get('image') or 'interact_pickup_drop',
        'equipped': False,
        'weight': entry.get('weight'),
        'size': entry.get('size'),
        'is_creature': True,
        'entity_uid': entry.get('entity_uid'),
    }


def _map_for(entity, battle=None, map_obj=None):
    if map_obj is not None:
        return map_obj
    if battle is not None:
        try:
            found = battle.map_for(entity)
            if found is not None:
                return found
        except Exception:
            pass
    session = getattr(entity, 'session', None)
    if session is not None:
        try:
            return session.map_for(entity)
        except Exception:
            return None
    return None


def _remove_from_world(creature, battle=None, map_obj=None):
    resolved_map = _map_for(creature, battle=battle, map_obj=map_obj)
    if battle is not None:
        try:
            battle.remove(creature, from_map=True)
        except Exception:
            if resolved_map is not None:
                resolved_map.remove(creature, battle=battle)
    elif resolved_map is not None:
        resolved_map.remove(creature)
    session = getattr(creature, 'session', None)
    if session is not None:
        pin = getattr(session.entity_registry, 'pin', None)
        if callable(pin):
            pin(creature)


def can_pickup_creature(carrier, creature, battle=None, map_obj=None, session=None):
    if carrier is None or creature is None or carrier is creature:
        return False, 'Invalid target'
    if not is_dead_portable_creature(creature):
        return False, 'Only dead creatures can be carried'
    resolved_map = _map_for(creature, battle=battle, map_obj=map_obj)
    if resolved_map is None:
        return False, 'Creature is not on the map'
    accept = getattr(carrier, 'can_accept_item', None)
    snapshot = _creature_item_stub(creature)
    if callable(accept):
        ok, reason = accept(snapshot['type'], 1, source_item=snapshot, session=session)
        if not ok:
            return False, reason
    return True, None


def pickup_creature(carrier, creature, battle=None, map_obj=None, session=None):
    """Remove a dead creature from the map and add it to *carrier* inventory."""
    ok, reason = can_pickup_creature(carrier, creature, battle=battle, map_obj=map_obj, session=session)
    if not ok:
        return False, reason
    snapshot = serialize_portable_creature(creature)
    _remove_from_world(creature, battle=battle, map_obj=map_obj)
    carrier.add_item(snapshot['type'], 1, source_item=snapshot)
    resolved_session = session or getattr(carrier, 'session', None) or getattr(creature, 'session', None)
    if resolved_session is not None and getattr(resolved_session, 'event_manager', None):
        resolved_session.event_manager.received_event({
            'event': 'message',
            'source': carrier,
            'target': creature,
            'message': f"{carrier.label()} picks up {_creature_label(creature)}.",
        })
    return True, None


def find_drop_position(map_obj, creature, origin):
    """Prefer *origin*; otherwise an adjacent empty square."""
    if map_obj is None or origin is None:
        return None
    ox, oy = int(origin[0]), int(origin[1])
    candidates = [(ox, oy)]
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            candidates.append((ox + dx, oy + dy))
    for nx, ny in candidates:
        try:
            if nx < 0 or ny < 0:
                continue
            if map_obj.placeable(creature, nx, ny, squeeze=False):
                return (nx, ny)
        except Exception:
            continue
    return None


def place_creature_from_item(session, entry, map_obj, origin, battle=None):
    """Restore a carried creature onto *map_obj* near *origin*."""
    creature = restore_portable_creature(session, entry)
    if creature is None:
        return None, 'Could not restore creature'
    position = find_drop_position(map_obj, creature, origin)
    if position is None:
        return None, 'No space to place the body'
    map_obj.place(position, creature, battle=battle)
    if session is not None:
        session.register_entity(creature)
        pin = getattr(session.entity_registry, 'pin', None)
        if callable(pin):
            pin(creature)
    return creature, None


def apply_carry_interaction(carrier, creature, battle=None, session=None):
    ok, reason = pickup_creature(carrier, creature, battle=battle, session=session)
    if ok:
        return True
    resolved_session = session or getattr(carrier, 'session', None) or getattr(creature, 'session', None)
    if resolved_session is not None and getattr(resolved_session, 'event_manager', None):
        resolved_session.event_manager.received_event({
            'event': 'message',
            'source': carrier,
            'target': creature,
            'message': reason or 'Cannot carry that.',
        })
    return True


def iter_inventory_creature_entries(entity):
    inventory = getattr(entity, 'inventory', None) or {}
    if not isinstance(inventory, dict):
        return
    for name, entry in inventory.items():
        if not isinstance(entry, dict):
            continue
        yield name, entry
        for content in entry.get('contents') or []:
            if isinstance(content, dict):
                yield content.get('type') or content.get('item'), content


def rehydrate_carried_creatures_in(session, entity):
    """Restore off-map corpses stored in *entity* inventory and pin them."""
    if session is None or entity is None:
        return
    for _name, entry in iter_inventory_creature_entries(entity):
        if not is_portable_creature_entry(entry, _name):
            continue
        try:
            restore_portable_creature(session, entry)
        except Exception:
            continue
