import copy


def snapshot_inventory_entry(entry, amount=None):
    """Build a detached inventory stack snapshot for transfers."""
    if not entry or not isinstance(entry, dict):
        return None

    try:
        stack_qty = int(entry.get('qty', 0) or 0)
    except (TypeError, ValueError):
        stack_qty = 0

    if amount is None:
        removed_qty = stack_qty
    else:
        try:
            removed_qty = max(0, int(amount))
        except (TypeError, ValueError):
            removed_qty = stack_qty
    if stack_qty > 0:
        removed_qty = min(removed_qty, stack_qty)

    item_type = entry.get('type') or entry.get('item')
    snapshot = {
        'type': item_type,
        'qty': removed_qty,
    }

    # Container contents move with the last unit removed from this stack.
    if stack_qty > 0 and removed_qty >= stack_qty:
        if entry.get('contents') is not None:
            snapshot['contents'] = copy.deepcopy(entry.get('contents', []))
        if entry.get('is_container'):
            snapshot['is_container'] = True

    return snapshot


def merge_inventory_entry(existing_entry, received_entry, amount=1):
    """Merge a received stack snapshot into an existing inventory entry."""
    try:
        add_qty = max(0, int(amount))
    except (TypeError, ValueError):
        add_qty = 0
    existing_entry['qty'] = int(existing_entry.get('qty', 0) or 0) + add_qty

    if not received_entry or not isinstance(received_entry, dict):
        return existing_entry

    received_contents = received_entry.get('contents')
    if received_contents is not None and not existing_entry.get('contents'):
        existing_entry['contents'] = copy.deepcopy(received_contents)
    if received_entry.get('is_container'):
        existing_entry['is_container'] = True
    return existing_entry


class Inventory:
    def _resolve_session(self, session=None):
        return session or getattr(self, 'session', None)

    def _item_definition(self, item_name, session=None):
        session = self._resolve_session(session)
        if session is None:
            return {}
        try:
            return session.load_thing(item_name) or {}
        except Exception:
            return {}

    def _item_weight_lbs(self, item_name, session=None, qty=1):
        definition = self._item_definition(item_name, session)
        try:
            weight = float(definition.get('weight') or 0)
        except (TypeError, ValueError):
            weight = 0.0
        try:
            amount = max(0, int(qty))
        except (TypeError, ValueError):
            amount = 1
        return weight * amount

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
                        'contents': [],
                    }
                self.inventory[inventory_type]['qty'] += inventory_qty
                if 'contents' in inventory:
                    existing_contents = self.inventory[inventory_type].get('contents', [])
                    for content_item in inventory.get('contents', []):
                        content_type = content_item.get('type') or content_item.get('item')
                        content_qty = content_item.get('qty', 1)
                        found = False
                        for ec in existing_contents:
                            if (ec.get('type') or ec.get('item')) == content_type:
                                ec['qty'] = ec.get('qty', 0) + content_qty
                                found = True
                                break
                        if not found:
                            existing_contents.append({
                                'type': content_type,
                                'qty': content_qty,
                            })
                    self.inventory[inventory_type]['contents'] = existing_contents
        self._ensure_container_flags(self._resolve_session())
        return self.inventory

    def _ensure_container_flags(self, session=None):
        if session is None:
            return
        for item_name, item_data in (self.inventory or {}).items():
            definition = self._item_definition(item_name, session)
            if definition.get('type') == 'container' or definition.get('container'):
                item_data.setdefault('contents', [])
                item_data['is_container'] = True

    def is_container(self, item_name, session=None):
        """Check if an item is a container (YAML type or stored contents)."""
        item_data = self.inventory.get(item_name)
        if not item_data:
            return False
        if item_data.get('contents') or item_data.get('is_container'):
            return True
        definition = self._item_definition(item_name, session)
        return definition.get('type') == 'container' or bool(definition.get('container'))

    def container_capacity_lbs(self, item_name, session=None):
        definition = self._item_definition(item_name, session)
        raw = definition.get('capacity_lbs', definition.get('capacity_weight_lbs'))
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def container_capacity_cu_ft(self, item_name, session=None):
        definition = self._item_definition(item_name, session)
        raw = definition.get('capacity_cu_ft', definition.get('capacity_volume_cu_ft'))
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def container_extradimensional(self, item_name, session=None):
        """True when container contents should not add to the carrier's encumbrance."""
        definition = self._item_definition(item_name, session)
        if definition.get('extradimensional') or definition.get('extradimensional_space'):
            return True
        if definition.get('contents_exclude_from_carry_weight'):
            return True
        return False

    def container_counts_toward_carry_weight(self, item_name, session=None):
        """Normal containers add their own weight plus contents; extradimensional do not."""
        return not self.container_extradimensional(item_name, session)

    def get_container_contents(self, item_name):
        item_data = self.inventory.get(item_name)
        if not item_data:
            return []
        return list(item_data.get('contents', []))

    def contents_weight(self, item_name, session=None):
        total = 0.0
        for content in self.get_container_contents(item_name):
            content_type = content.get('type') or content.get('item')
            if not content_type:
                continue
            total += self._item_weight_lbs(content_type, session, content.get('qty', 1))
        return total

    def container_status(self, item_name, session=None):
        session = self._resolve_session(session)
        contents = self.get_container_contents(item_name)
        weight_used = self.contents_weight(item_name, session)
        capacity_lbs = self.container_capacity_lbs(item_name, session)
        capacity_cu_ft = self.container_capacity_cu_ft(item_name, session)
        enriched = []
        for content in contents:
            content_type = content.get('type') or content.get('item')
            definition = self._item_definition(content_type, session)
            enriched.append({
                'type': content_type,
                'qty': content.get('qty', 1),
                'label': definition.get('label') or definition.get('name') or content_type,
                'weight': definition.get('weight'),
                'weight_total': self._item_weight_lbs(content_type, session, content.get('qty', 1)),
            })
        return {
            'container': item_name,
            'label': self._item_definition(item_name, session).get('label')
            or self._item_definition(item_name, session).get('name')
            or item_name,
            'contents': enriched,
            'weight_used_lbs': round(weight_used, 2),
            'capacity_lbs': capacity_lbs,
            'capacity_cu_ft': capacity_cu_ft,
            'weight_remaining_lbs': None if capacity_lbs is None else round(max(0.0, capacity_lbs - weight_used), 2),
            'extradimensional': self.container_extradimensional(item_name, session),
            'counts_toward_carry_weight': self.container_counts_toward_carry_weight(item_name, session),
        }

    def can_fit_in_container(self, item_name, content_item, content_qty=1, session=None):
        session = self._resolve_session(session)
        if not self.is_container(item_name, session):
            if item_name not in (self.inventory or {}):
                return False, 'Item is not a container'
            if session is not None:
                definition = self._item_definition(item_name, session)
                if definition.get('type') != 'container' and not definition.get('container'):
                    return False, 'Item is not a container'
        if content_item == item_name:
            return False, 'A container cannot hold itself'
        if self.is_container(content_item, session):
            return False, 'Nested containers are not supported'
        try:
            qty = max(1, int(content_qty))
        except (TypeError, ValueError):
            qty = 1

        if session is None:
            return True, None

        definition = self._item_definition(content_item, session)
        if not definition:
            return False, f'Unknown item: {content_item}'

        added_weight = self._item_weight_lbs(content_item, session, qty)
        capacity_lbs = self.container_capacity_lbs(item_name, session)
        if capacity_lbs is not None:
            projected = self.contents_weight(item_name, session) + added_weight
            if projected > capacity_lbs + 1e-6:
                remaining = max(0.0, capacity_lbs - self.contents_weight(item_name, session))
                return False, (
                    f'Not enough room in {item_name} '
                    f'({remaining:.1f} lb remaining of {capacity_lbs:.0f} lb capacity)'
                )

        capacity_cu_ft = self.container_capacity_cu_ft(item_name, session)
        item_bulk = definition.get('bulk_cu_ft', definition.get('volume_cu_ft'))
        if capacity_cu_ft is not None and item_bulk is not None:
            try:
                added_volume = float(item_bulk) * qty
            except (TypeError, ValueError):
                added_volume = 0.0
            used_volume = 0.0
            for content in self.get_container_contents(item_name):
                content_type = content.get('type') or content.get('item')
                content_def = self._item_definition(content_type, session)
                bulk = content_def.get('bulk_cu_ft', content_def.get('volume_cu_ft'))
                if bulk is None:
                    continue
                try:
                    used_volume += float(bulk) * int(content.get('qty', 1))
                except (TypeError, ValueError):
                    continue
            if used_volume + added_volume > capacity_cu_ft + 1e-6:
                return False, f'Not enough space in {item_name} ({capacity_cu_ft:.1f} cu ft capacity)'

        return True, None

    def add_to_container(self, item_name, content_item, content_qty=1, session=None):
        ok, _reason = self.add_to_container_checked(item_name, content_item, content_qty, session=session)
        return ok

    def add_to_container_checked(self, item_name, content_item, content_qty=1, session=None):
        session = self._resolve_session(session)
        can_fit, reason = self.can_fit_in_container(item_name, content_item, content_qty, session=session)
        if not can_fit:
            return False, reason

        if not self.is_container(item_name, session):
            if item_name in self.inventory:
                self.inventory[item_name]['contents'] = []
                self.inventory[item_name]['is_container'] = True
            else:
                return False, 'Container not found in inventory'

        try:
            qty = max(1, int(content_qty))
        except (TypeError, ValueError):
            qty = 1

        contents = self.inventory[item_name].get('contents', [])
        for content in contents:
            if (content.get('type') or content.get('item')) == content_item:
                content['qty'] = content.get('qty', 0) + qty
                self.inventory[item_name]['contents'] = contents
                return True, None

        contents.append({'type': content_item, 'qty': qty})
        self.inventory[item_name]['contents'] = contents
        return True, None

    def remove_from_container(self, item_name, content_item, content_qty=1):
        contents = self.inventory.get(item_name, {}).get('contents', [])
        try:
            qty = max(1, int(content_qty))
        except (TypeError, ValueError):
            qty = 1

        for index, content in enumerate(contents):
            if (content.get('type') or content.get('item')) == content_item:
                current_qty = content.get('qty', 0)
                if current_qty <= qty:
                    contents.pop(index)
                else:
                    content['qty'] = current_qty - qty
                self.inventory[item_name]['contents'] = contents
                return True
        return False

    def stowable_inventory_items(self, container_name, session=None):
        """Top-level inventory items that may be placed into a container."""
        session = self._resolve_session(session)
        stowable = []
        equipped_names = set()
        if hasattr(self, 'equipped_items'):
            try:
                equipped_names = {item.get('name') for item in self.equipped_items() if item.get('name')}
            except Exception:
                equipped_names = set()

        for item_name, item_data in (self.inventory or {}).items():
            if item_name == container_name:
                continue
            if item_name in equipped_names:
                continue
            if self.is_container(item_name, session):
                continue
            qty = int(item_data.get('qty', 0) or 0)
            if qty <= 0:
                continue
            definition = self._item_definition(item_name, session)
            stowable.append({
                'name': item_name,
                'label': definition.get('label') or definition.get('name') or item_name,
                'qty': qty,
                'weight': definition.get('weight'),
            })
        return stowable

    def stow_item(self, container_name, item_name, qty=1, session=None):
        session = self._resolve_session(session)
        try:
            amount = max(1, int(qty))
        except (TypeError, ValueError):
            amount = 1

        inventory_entry = self.inventory.get(item_name)
        if not inventory_entry or int(inventory_entry.get('qty', 0) or 0) < amount:
            return False, 'Not enough of that item in your inventory'

        ok, reason = self.add_to_container_checked(container_name, item_name, amount, session=session)
        if not ok:
            return False, reason

        self.deduct_item(item_name, amount)
        return True, None

    def retrieve_item(self, container_name, item_name, qty=1, session=None):
        session = self._resolve_session(session)
        try:
            amount = max(1, int(qty))
        except (TypeError, ValueError):
            amount = 1

        if not self.remove_from_container(container_name, item_name, amount):
            return False, 'Item not found in container'

        self.add_item(item_name, amount)
        return True, None

    def carry_weight_status(self, session=None):
        """Summarize carried weight for UI and encumbrance checks."""
        session = self._resolve_session(session)
        items_weight = 0.0
        equipped_weight = 0.0

        if hasattr(self, 'inventory_items'):
            for item in self.inventory_items(session):
                try:
                    weight = float(item.get('weight') or 0)
                    qty = int(item.get('qty', 1) or 1)
                except (TypeError, ValueError):
                    weight = 0.0
                    qty = 1
                items_weight += weight * qty
        else:
            for item_name, item_data in (self.inventory or {}).items():
                try:
                    qty = int(item_data.get('qty', 0) or 0)
                except (TypeError, ValueError):
                    qty = 0
                if qty <= 0:
                    continue
                items_weight += self._item_weight_lbs(item_name, session, qty)

        if hasattr(self, 'equipped_items'):
            for item in self.equipped_items():
                try:
                    equipped_weight += float(item.get('weight') or 0)
                except (TypeError, ValueError):
                    continue

        container_contents_weight = self.nested_inventory_weight(session)
        total_weight = items_weight + equipped_weight + container_contents_weight

        capacity = None
        if hasattr(self, 'carry_capacity'):
            try:
                capacity = float(self.carry_capacity())
            except Exception:
                capacity = None

        extradimensional = []
        for item_name in (self.inventory or {}):
            if not self.is_container(item_name, session):
                continue
            if not self.container_extradimensional(item_name, session):
                continue
            contents_weight = self.contents_weight(item_name, session)
            definition = self._item_definition(item_name, session)
            try:
                container_weight = float(definition.get('weight') or 0)
            except (TypeError, ValueError):
                container_weight = 0.0
            extradimensional.append({
                'name': item_name,
                'label': definition.get('label') or definition.get('name') or item_name,
                'contents_weight_lbs': round(contents_weight, 2),
                'carry_weight_lbs': round(container_weight, 2),
            })

        return {
            'weight_lbs': round(total_weight, 1),
            'items_weight_lbs': round(items_weight, 1),
            'equipped_weight_lbs': round(equipped_weight, 1),
            'container_contents_weight_lbs': round(container_contents_weight, 1),
            'carry_capacity_lbs': capacity,
            'remaining_lbs': None if capacity is None else round(max(0.0, capacity - total_weight), 1),
            'over_capacity': capacity is not None and total_weight > capacity + 1e-6,
            'encumbered': capacity is not None and total_weight > capacity + 1e-6,
            'heavily_encumbered': capacity is not None and total_weight > (capacity * 2.0) + 1e-6,
            'extradimensional_containers': extradimensional,
            'strength': (getattr(self, 'ability_scores', None) or {}).get('str'),
        }

    def nested_inventory_weight(self, session=None):
        session = self._resolve_session(session)
        total = 0.0
        for item_name in (self.inventory or {}):
            if not self.is_container(item_name, session):
                continue
            if self.container_extradimensional(item_name, session):
                continue
            total += self.contents_weight(item_name, session)
        return total
