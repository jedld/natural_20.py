import unittest

from natural20.concern.container import Container
from natural20.concern.inventory import Inventory, merge_inventory_entry, snapshot_inventory_entry
from natural20.event_manager import EventManager
from natural20.entity import Entity
from natural20.session import Session


class TestInventoryTransferSnapshots(unittest.TestCase):
    def test_snapshot_copies_container_contents(self):
        entry = {
            'type': 'backpack',
            'qty': 1,
            'is_container': True,
            'contents': [{'type': 'rope', 'qty': 1}],
        }
        snap = snapshot_inventory_entry(entry, 1)
        self.assertEqual(snap['qty'], 1)
        self.assertEqual(snap['contents'], [{'type': 'rope', 'qty': 1}])
        snap['contents'][0]['qty'] = 99
        self.assertEqual(entry['contents'][0]['qty'], 1)

    def test_snapshot_omits_contents_for_partial_stack_removal(self):
        entry = {
            'type': 'arrow',
            'qty': 10,
            'contents': [{'type': 'rope', 'qty': 1}],
        }
        snap = snapshot_inventory_entry(entry, 3)
        self.assertEqual(snap['qty'], 3)
        self.assertNotIn('contents', snap)

    def test_merge_inventory_entry_preserves_container_payload(self):
        existing = {'type': 'backpack', 'qty': 0}
        received = {
            'type': 'backpack',
            'qty': 1,
            'is_container': True,
            'contents': [{'type': 'torch', 'qty': 2}],
        }
        merge_inventory_entry(existing, received, 1)
        self.assertEqual(existing['qty'], 1)
        self.assertTrue(existing['is_container'])
        self.assertEqual(existing['contents'], [{'type': 'torch', 'qty': 2}])


class _TransferEntity(Entity, Container, Inventory):
    def __init__(self, session, name):
        self.session = session
        self.inventory = {}
        self.name = name
        self.entity_event_hooks = {}

    def label(self):
        return self.name

    def equipped_items(self):
        return []


class TestContainerTransferBetweenEntities(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = Session(root_path='templates', event_manager=EventManager())

    def _entity(self, name):
        return _TransferEntity(self.session, name)

    def test_transfer_preserves_backpack_contents(self):
        giver = self._entity('giver')
        receiver = self._entity('receiver')
        giver.inventory = {
            'backpack': {
                'type': 'backpack',
                'qty': 1,
                'is_container': True,
                'contents': [{'type': 'rope', 'qty': 1}, {'type': 'torch', 'qty': 3}],
            }
        }

        transfer = Container()
        transfer.transfer(
            None,
            giver,
            receiver,
            {
                'from': {'items': [], 'qty': []},
                'to': {'items': ['backpack'], 'qty': ['1']},
            },
        )

        self.assertNotIn('backpack', giver.inventory)
        self.assertIn('backpack', receiver.inventory)
        contents = receiver.get_container_contents('backpack')
        content_types = {row['type']: row['qty'] for row in contents}
        self.assertEqual(content_types['rope'], 1)
        self.assertEqual(content_types['torch'], 3)

    def test_deduct_and_add_item_roundtrip(self):
        giver = _TransferEntity(self.session, 'giver')
        receiver = _TransferEntity(self.session, 'receiver')
        giver.inventory = {
            'bag_of_holding': {
                'type': 'bag_of_holding',
                'qty': 1,
                'is_container': True,
                'contents': [{'type': 'rope', 'qty': 2}],
            }
        }

        removed = giver.deduct_item('bag_of_holding', 1)
        receiver.add_item('bag_of_holding', 1, source_item=removed)

        self.assertNotIn('bag_of_holding', giver.inventory)
        self.assertEqual(receiver.get_container_contents('bag_of_holding')[0]['qty'], 2)


if __name__ == '__main__':
    unittest.main()
