"""Helpers for D&D 5e pickpocket stealable item filtering.

PHB 2014: a successful pickpocket steals one *small* object from the target.
We treat backpack inventory entries as stealable when they are explicitly
marked ``pickpocketable`` in YAML, or when item weight is at most
``MAX_PICKPOCKET_WEIGHT_LB`` (default 1 lb). Equipped gear is excluded.
"""

from __future__ import annotations

MAX_PICKPOCKET_WEIGHT_LB = 1.0

_PICKPOCKETABLE_TYPES = frozenset({
    'coin',
    'currency',
    'gem',
    'trinket',
    'potion',
    'scroll',
    'ring',
    'amulet',
    'key',
})


def _item_weight(item_def, entry=None):
    if entry and entry.get('weight') is not None:
        try:
            return float(entry['weight'])
        except (TypeError, ValueError):
            pass
    if item_def and item_def.get('weight') is not None:
        try:
            return float(item_def['weight'])
        except (TypeError, ValueError):
            pass
    return None


def is_pickpocketable_item(item_def, *, entry=None):
    """Return True when an inventory entry may be stolen via pickpocket."""
    if not item_def:
        return False
    if item_def.get('pickpocketable') is False:
        return False
    if item_def.get('pickpocketable') is True:
        return True

    item_type = str(item_def.get('type') or item_def.get('subtype') or '').lower()
    if item_type in _PICKPOCKETABLE_TYPES:
        return True

    weight = _item_weight(item_def, entry=entry)
    if weight is not None and weight <= MAX_PICKPOCKET_WEIGHT_LB:
        return True
    return False


def pickpocketable_inventory_items(session, target):
    """List stealable items from the target's unequipped inventory."""
    if target is None or not getattr(target, 'inventory', None):
        return []

    equipped_names = set()
    if hasattr(target, 'equipped_items'):
        try:
            equipped_names = {
                str(item.get('name') or item.get('type') or '')
                for item in (target.equipped_items() or [])
            }
        except Exception:
            equipped_names = set()

    items = []
    for name, entry in target.inventory.items():
        qty = (entry or {}).get('qty', 0)
        if qty <= 0:
            continue
        if str(name) in equipped_names:
            continue

        item_def = session.load_thing(name)
        row = {
            'name': str(name),
            'label': (entry or {}).get('label') or (
                (item_def.get('label') if item_def else None)
                or (item_def.get('name') if item_def else None)
                or str(name)
            ),
            'qty': qty,
            'image': (item_def or {}).get('image', name),
            'weight': _item_weight(item_def, entry=entry),
        }
        if is_pickpocketable_item(item_def, entry=row):
            items.append(row)

    items.sort(key=lambda row: row['label'].lower())
    return items


def resolve_inventory_item_name(session, target, item_name):
    """Resolve a UI label or key to the target inventory key."""
    if not item_name or target is None or not getattr(target, 'inventory', None):
        return None

    if item_name in target.inventory and target.inventory[item_name].get('qty', 0) > 0:
        return item_name

    needle = str(item_name).lower()
    for key, entry in target.inventory.items():
        if entry.get('qty', 0) <= 0:
            continue
        if str(key).lower() == needle:
            return key
        label = entry.get('label') or str(key)
        if str(label).lower() == needle:
            return key
        item_def = session.load_thing(key)
        if item_def:
            def_label = item_def.get('label') or item_def.get('name')
            if def_label and str(def_label).lower() == needle:
                return key
    return None


def item_display_name(session, item_name):
    """Return a player-facing label for an inventory key."""
    if not item_name:
        return 'an item'
    if session is not None:
        try:
            item_def = session.load_thing(item_name)
        except Exception:
            item_def = None
        if item_def:
            return item_def.get('label') or item_def.get('name') or str(item_name)
    return str(item_name)
