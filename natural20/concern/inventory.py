class Inventory:
    def load_inventory(self):
        self.inventory = {}
        for inventory in self.properties.get('inventory', []):
            inventory_type = inventory.get('type') or inventory.get('item')
            inventory_qty = inventory.get('qty', 1)
            if inventory_type:
                if inventory_type not in self.inventory:
                    self.inventory[inventory_type] = {
                        'type': inventory_type,
                        'qty': 0,
                        'contents': []  # For container items
                    }
                self.inventory[inventory_type]['qty'] += inventory_qty
                # Merge contents if present
                if 'contents' in inventory:
                    existing_contents = self.inventory[inventory_type].get('contents', [])
                    for content_item in inventory.get('contents', []):
                        content_type = content_item.get('type') or content_item.get('item')
                        content_qty = content_item.get('qty', 1)
                        # Check if this content already exists
                        found = False
                        for ec in existing_contents:
                            if (ec.get('type') or ec.get('item')) == content_type:
                                ec['qty'] = ec.get('qty', 0) + content_qty
                                found = True
                                break
                        if not found:
                            existing_contents.append({
                                'type': content_type,
                                'qty': content_qty
                            })
                    self.inventory[inventory_type]['contents'] = existing_contents
        return self.inventory

    def is_container(self, item_name):
        """Check if an item is a container (has contents capability)."""
        item_data = self.inventory.get(item_name)
        if not item_data:
            return False
        # Check if item has contents or is marked as container type
        return bool(item_data.get('contents')) or item_data.get('is_container', False)

    def get_container_contents(self, item_name):
        """Get the contents of a container item."""
        item_data = self.inventory.get(item_name)
        if not item_data:
            return []
        return item_data.get('contents', [])

    def add_to_container(self, item_name, content_item, content_qty=1):
        """Add an item to a container."""
        if not self.is_container(item_name):
            # Auto-initialize as container if needed
            if item_name in self.inventory:
                self.inventory[item_name]['contents'] = []
                self.inventory[item_name]['is_container'] = True
            else:
                return False
        
        contents = self.inventory[item_name].get('contents', [])
        
        # Check if content already exists in container
        for content in contents:
            if (content.get('type') or content.get('item')) == content_item:
                content['qty'] = content.get('qty', 0) + content_qty
                return True
        
        # Add new content
        contents.append({
            'type': content_item,
            'qty': content_qty
        })
        self.inventory[item_name]['contents'] = contents
        return True

    def remove_from_container(self, item_name, content_item, content_qty=1):
        """Remove an item from a container."""
        contents = self.inventory.get(item_name, {}).get('contents', [])
        
        for i, content in enumerate(contents):
            if (content.get('type') or content.get('item')) == content_item:
                current_qty = content.get('qty', 0)
                if current_qty <= content_qty:
                    contents.pop(i)
                else:
                    content['qty'] = current_qty - content_qty
                self.inventory[item_name]['contents'] = contents
                return True
        return False
