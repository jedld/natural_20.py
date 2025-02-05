import pdb
class Container:
    def store(self, battle, source, target, items):
        for item_with_count in items:
            item, qty = item_with_count
            source_item = source.deduct_item(item.name, qty)
            target.add_item(item.name, qty, source_item)
            battle.trigger_event("object_received", target, item_type=item.name)

    def transfer(self, battle, source, target, items):
        for direction, (src, dst) in [('from', (target, source)), ('to', (source, target))]:
            for item, qty in zip(items[direction]['items'], items[direction]['qty']):
                if item in src.inventory:
                    if qty==0:
                        continue
                    src.deduct_item(item, int(qty))
                    dst.add_item(item, int(qty))
                    if battle:
                        battle.trigger_event("object_received", dst, item_type=item)
