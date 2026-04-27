"""Phase 4 tests for ResourcePool."""

import unittest

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.resource_pool import ResourcePool


class TestResourcePool(unittest.TestCase):
    def test_basic_consume_and_restore(self):
        p = ResourcePool('inspiration', 4, restore_on='long_rest')
        self.assertTrue(p.available(1))
        self.assertTrue(p.consume(2))
        self.assertEqual(p.current, 2)
        self.assertFalse(p.consume(3))
        p.restore()
        self.assertEqual(p.current, 4)

    def test_restore_for_matches_kind(self):
        p = ResourcePool('ki', 3, restore_on='short_rest')
        p.consume(2)
        self.assertFalse(p.restore_for('long_rest'))
        self.assertEqual(p.current, 1)
        self.assertTrue(p.restore_for('short_rest'))
        self.assertEqual(p.current, 3)

    def test_invalid_restore_kind(self):
        with self.assertRaises(ValueError):
            ResourcePool('x', 1, restore_on='nope')

    def test_round_trip(self):
        p = ResourcePool('rage', 3, restore_on='long_rest', current=1)
        data = p.to_dict()
        q = ResourcePool.from_dict(data)
        self.assertEqual(q.name, 'rage')
        self.assertEqual(q.max_value, 3)
        self.assertEqual(q.current, 1)
        self.assertEqual(q.restore_on, 'long_rest')


class TestEntityResourceAPI(unittest.TestCase):
    def make_session(self):
        em = EventManager()
        em.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=em)

    def setUp(self):
        self.session = self.make_session()
        self.entity = PlayerCharacter.load(self.session, 'high_elf_mage.yml')

    def test_register_and_consume(self):
        pool = self.entity.register_resource('inspiration', 3, restore_on='short_rest')
        self.assertIs(self.entity.get_resource('inspiration'), pool)
        self.assertEqual(self.entity.resource_value('inspiration'), 3)
        self.assertTrue(self.entity.consume_resource('inspiration', 2))
        self.assertEqual(self.entity.resource_value('inspiration'), 1)
        self.assertFalse(self.entity.consume_resource('inspiration', 5))

    def test_unknown_resource(self):
        self.assertEqual(self.entity.resource_value('absent'), 0)
        self.assertFalse(self.entity.has_resource('absent'))
        self.assertFalse(self.entity.consume_resource('absent'))

    def test_short_rest_restores_short_rest_pools(self):
        self.entity.register_resource('chan_div', 1, restore_on='short_rest')
        self.entity.register_resource('rage', 2, restore_on='long_rest')
        self.entity.consume_resource('chan_div')
        self.entity.consume_resource('rage')
        self.entity.short_rest(None, force=True)
        self.assertEqual(self.entity.resource_value('chan_div'), 1)
        self.assertEqual(self.entity.resource_value('rage'), 1)

    def test_long_rest_restores_long_rest_pools(self):
        self.entity.register_resource('rage', 2, restore_on='long_rest')
        self.entity.consume_resource('rage', 2)
        self.entity.long_rest()
        self.assertEqual(self.entity.resource_value('rage'), 2)

    def test_round_trip_through_pc_serialization(self):
        self.entity.register_resource('inspiration', 4, restore_on='long_rest')
        self.entity.consume_resource('inspiration', 1)
        data = self.entity.to_dict()
        rehydrated = PlayerCharacter.from_dict(data)
        self.assertEqual(rehydrated.resource_value('inspiration'), 3)
        pool = rehydrated.get_resource('inspiration')
        self.assertEqual(pool.max_value, 4)
        self.assertEqual(pool.restore_on, 'long_rest')


if __name__ == '__main__':
    unittest.main()
