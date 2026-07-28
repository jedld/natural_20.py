import unittest

from natural20.concern.inventory import Inventory
from natural20.event_manager import EventManager
from natural20.session import Session


class _InvHolder(Inventory):
    def __init__(self, session=None):
        self.properties = {}
        self.inventory = {}
        self.session = session

    def equipped_items(self):
        return []

    def add_item(self, item_name, qty=1, source_item=None):
        entry = self.inventory.setdefault(item_name, {'type': item_name, 'qty': 0})
        entry['qty'] = int(entry.get('qty', 0) or 0) + int(qty)

    def deduct_item(self, item_name, qty=1):
        entry = self.inventory.get(item_name)
        if not entry:
            return False
        current = int(entry.get('qty', 0) or 0)
        if current < qty:
            return False
        entry['qty'] = current - qty
        if entry['qty'] <= 0:
            self.inventory.pop(item_name, None)
        return True


class TestContainerCapacity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = Session(root_path='templates', event_manager=EventManager())

    def setUp(self):
        self.inv = _InvHolder(session=self.session)
        self.inv.inventory = {
            'backpack': {'type': 'backpack', 'qty': 1, 'contents': [], 'is_container': True},
            'torch': {'type': 'torch', 'qty': 5},
            'rope': {'type': 'rope', 'qty': 1},
        }

    def test_backpack_detected_from_yaml(self):
        self.assertTrue(self.inv.is_container('backpack', self.session))

    def test_container_capacity_from_yaml(self):
        self.assertEqual(self.inv.container_capacity_lbs('backpack', self.session), 30.0)
        self.assertEqual(self.inv.container_capacity_cu_ft('backpack', self.session), 1.0)

    def test_stow_and_retrieve_item(self):
        ok, reason = self.inv.stow_item('backpack', 'torch', 2, self.session)
        self.assertTrue(ok, reason)
        self.assertEqual(self.inv.inventory['torch']['qty'], 3)
        contents = self.inv.get_container_contents('backpack')
        self.assertEqual(contents[0]['qty'], 2)

        ok, reason = self.inv.retrieve_item('backpack', 'torch', 1, self.session)
        self.assertTrue(ok, reason)
        self.assertEqual(self.inv.inventory['torch']['qty'], 4)
        self.assertEqual(self.inv.get_container_contents('backpack')[0]['qty'], 1)

    def test_capacity_blocks_overweight_stow(self):
        self.inv.inventory['rope'] = {'type': 'rope', 'qty': 4}
        ok, reason = self.inv.stow_item('backpack', 'rope', 3, self.session)
        self.assertTrue(ok, reason)
        ok, reason = self.inv.stow_item('backpack', 'rope', 1, self.session)
        self.assertFalse(ok)
        self.assertIn('Not enough room', reason)
        self.assertEqual(self.inv.inventory['rope']['qty'], 1)

    def test_nested_inventory_weight_counts_contents(self):
        self.inv.inventory['rope'] = {'type': 'rope', 'qty': 2}
        ok, reason = self.inv.stow_item('backpack', 'rope', 2, self.session)
        self.assertTrue(ok, reason)
        weight = self.inv.nested_inventory_weight(self.session)
        self.assertEqual(weight, 20.0)

    def test_cannot_stow_container_inside_container(self):
        self.inv.inventory['pouch'] = {'type': 'pouch', 'qty': 1, 'is_container': True, 'contents': []}
        ok, reason = self.inv.add_to_container_checked('backpack', 'pouch', 1, session=self.session)
        self.assertFalse(ok)
        self.assertIn('Nested containers', reason)

    def test_bag_of_holding_excludes_contents_from_carry_weight(self):
        self.inv.inventory = {
            'bag_of_holding': {
                'type': 'bag_of_holding',
                'qty': 1,
                'contents': [{'type': 'rope', 'qty': 5}],
                'is_container': True,
            },
        }
        status = self.inv.carry_weight_status(self.session)
        self.assertEqual(status['container_contents_weight_lbs'], 0.0)
        self.assertEqual(status['weight_lbs'], 15.0)
        self.assertEqual(len(status['extradimensional_containers']), 1)
        self.assertEqual(status['extradimensional_containers'][0]['contents_weight_lbs'], 50.0)

    def test_backpack_contents_count_toward_carry_weight(self):
        self.inv.inventory = {
            'backpack': {'type': 'backpack', 'qty': 1, 'contents': [{'type': 'rope', 'qty': 1}], 'is_container': True},
        }
        status = self.inv.carry_weight_status(self.session)
        self.assertEqual(status['weight_lbs'], 15.0)
        self.assertEqual(status['container_contents_weight_lbs'], 10.0)


if __name__ == '__main__':
    unittest.main()
