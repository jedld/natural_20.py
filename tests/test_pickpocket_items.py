"""Tests for natural20/utils/pickpocket_items.py."""

import unittest

from natural20.event_manager import EventManager
from natural20.session import Session
from natural20.utils.pickpocket_items import (
    is_pickpocketable_item,
    pickpocketable_inventory_items,
    resolve_inventory_item_name,
)


class TestPickpocketItems(unittest.TestCase):
    def setUp(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        self.session = Session(root_path='tests/fixtures', event_manager=event_manager)
        self.goblin = self.session.npc('goblin')

    def test_goblin_arrows_are_pickpocketable(self):
        items = pickpocketable_inventory_items(self.session, self.goblin)
        names = {row['name'] for row in items}
        self.assertIn('arrows', names)

    def test_heavy_armor_not_pickpocketable(self):
        chain_mail = self.session.load_equipment('chain_mail')
        self.assertFalse(is_pickpocketable_item(chain_mail))

    def test_explicit_pickpocketable_flag(self):
        self.assertTrue(is_pickpocketable_item({'pickpocketable': True, 'weight': 50}))
        self.assertFalse(is_pickpocketable_item({'pickpocketable': False, 'weight': 0.1}))

    def test_resolve_inventory_item_name(self):
        resolved = resolve_inventory_item_name(self.session, self.goblin, 'arrows')
        self.assertEqual(resolved, 'arrows')
