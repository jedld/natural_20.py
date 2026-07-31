"""Key matching for doors, chests, and other lockable objects."""


def entity_has_key(entity, key_name):
    """True when *entity* holds *key_name* or a master key whose ``opens`` list includes it."""
    if not entity or not key_name:
        return False
    if entity.item_count(key_name) > 0:
        return True
    session = getattr(entity, 'session', None)
    inventory = getattr(entity, 'inventory', None) or {}
    if session is None or not inventory:
        return False
    for carried_type, entry in inventory.items():
        try:
            qty = int((entry or {}).get('qty') or 0)
        except (TypeError, ValueError):
            qty = 0
        if qty <= 0:
            continue
        try:
            item_def = session.load_equipment(carried_type) or {}
        except Exception:
            continue
        opens = item_def.get('opens')
        if isinstance(opens, (list, tuple, set)) and key_name in opens:
            return True
    return False
