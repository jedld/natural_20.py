class Container:
    def store(self, battle, source, target, items):
        for item_with_count in items:
            item, qty = item_with_count
            source_item = source.deduct_item(item.name, qty)
            target.add_item(item.name, qty, source_item)
            battle.trigger_event("object_received", target, item_type=item.name)

    def retrieve(self, battle, source, target, items):
        for item_with_count in items:
            item, qty = item_with_count
            if item.equipped:
                self.unequip(item.name, transfer_inventory=False)
                source.add_item(item.name)
            else:
                source_item = target.deduct_item(item.name, qty)
                source.add_item(item.name, qty, source_item)
                battle.trigger_event("object_received", source, item_type=item.name)
