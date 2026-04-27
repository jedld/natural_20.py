import pdb
class Container:
    def store(self, battle, source, target, items):
        # Backwards-compat: legacy callers passed a list of (item, qty) tuples
        # representing a one-way deposit from source -> target. The web UI now
        # sends the same bidirectional ``{'from': ..., 'to': ...}`` dict used
        # by ``transfer`` so the loot modal can both take and deposit in a
        # single exchange. Detect the dict shape and delegate.
        if isinstance(items, dict) and ('from' in items or 'to' in items):
            return self.transfer(battle, source, target, items)
        for item_with_count in items or []:
            item, qty = item_with_count
            if item not in source.inventory:
                continue

            if qty == 0:
                continue

            if qty > source.inventory[item]['qty']:
                qty = source.inventory[item]['qty']

            source_item = source.deduct_item(item.name, qty)
            target.add_item(item.name, qty, source_item)
            battle.trigger_event("object_received", target, { "item_type" : item.name, "qty" : qty })

    def transfer(self, battle, source, target, items):
        # {'from': {'items': ['healing_potion', 'arrows'], 'qty': ['1', '20']}, 'to': {'items': ['dagger', 'arrows', 'thieves_tools', 'healing_potion'], 'qty': ['0', '0', '0', '0']}}
        # If no items were specified (e.g., automated interactions without UI selection), do nothing safely
        if not items or not isinstance(items, dict):
            return

        for direction, (src, dst) in [('from', (target, source)), ('to', (source, target))]:
            dir_payload = items.get(direction) or {}
            dir_items = dir_payload.get('items', []) or []
            dir_qtys = dir_payload.get('qty', []) or []
            for item, qty in zip(dir_items, dir_qtys):
                try:
                    qty = int(qty)
                except (TypeError, ValueError):
                    # Skip invalid quantities
                    continue
                print(f"transferring {item} -> {dst.label()} {qty} times")
                if item in getattr(src, 'inventory', {}):
                    if qty == 0:
                        continue

                    if qty > src.inventory[item]['qty']:
                        qty = src.inventory[item]['qty']

                    src.deduct_item(item, qty)
                    dst.add_item(item, qty)
                    print(f"triggering {item} -> {dst.label()} {qty} times")
                    # Triggers on the source object if supported
                    if hasattr(src, 'resolve_trigger'):
                        src.resolve_trigger(f"{item}_taken", { "target": target })
                        src.resolve_trigger("items_taken", { "target": target })
                    if battle:
                        battle.trigger_event("object_received", dst, { "item_type" :item, "qty" : qty })
