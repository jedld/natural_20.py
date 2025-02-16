import pdb
class Container:
    def store(self, battle, source, target, items):
        for item_with_count in items:
            item, qty = item_with_count
            if item not in source.inventory:
                continue

            if qty == 0:
                continue

            if qty > source.inventory[item]['qty']:
                qty = source.inventory[item]['qty']

            source_item = source.deduct_item(item.name, qty)
            target.add_item(item.name, qty, source_item)
            battle.trigger_event("object_received", target, item_type=item.name)

    def transfer(self, battle, source, target, items):
        # {'from': {'items': ['healing_potion', 'arrows'], 'qty': ['1', '20']}, 'to': {'items': ['dagger', 'arrows', 'thieves_tools', 'healing_potion'], 'qty': ['0', '0', '0', '0']}}
        for direction, (src, dst) in [('from', (target, source)), ('to', (source, target))]:
            for item, qty in zip(items[direction]['items'], items[direction]['qty']):
                qty = int(qty)
                if item in src.inventory:
                    if qty==0:
                        continue

                    if qty > src.inventory[item]['qty']:
                        qty = src.inventory[item]['qty']

                    src.deduct_item(item, qty)
                    dst.add_item(item, qty)
                    if battle:
                        battle.trigger_event("object_received", dst, item_type=item)
