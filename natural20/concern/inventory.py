class Inventory:
        
    def load_inventory(self):
        self.inventory = {}
        for inventory in self.properties.get('inventory', []):
            inventory_type = inventory.get('type')
            inventory_qty = inventory.get('qty')
            if inventory_type:
                if inventory_type not in self.inventory:
                    self.inventory[inventory_type] = {'type': inventory_type, 'qty': 0}
                    self.inventory[inventory_type]['qty'] += inventory_qty
        return self.inventory
