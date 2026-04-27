"""Tests for Battle's reaction trigger registry (Phase 3)."""

import unittest

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter


class TestReactionRegistry(unittest.TestCase):
    def setUp(self):
        em = EventManager()
        self.session = Session(root_path='tests/fixtures', event_manager=em)
        self.battle_map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.battle_map)
        self.cleric = PlayerCharacter.load(self.session, 'dwarf_cleric.yml')
        self.battle.add(self.cleric, 'a', position=[0, 5])

    def test_register_and_fire_reaction(self):
        called = []

        def handler(battle, ctx):
            called.append(ctx.get('marker'))
            return [{'event': 'fired', 'marker': ctx.get('marker')}]

        self.battle.register_reaction_trigger('attack_roll', handler)
        events = self.battle.fire_reaction_window('attack_roll', {'marker': 'x'})
        self.assertEqual(called, ['x'])
        self.assertEqual(events, [{'event': 'fired', 'marker': 'x'}])

    def test_priority_order_high_first(self):
        order = []

        def low(battle, ctx):
            order.append('low')

        def high(battle, ctx):
            order.append('high')

        self.battle.register_reaction_trigger('damage_taken', low, priority=1)
        self.battle.register_reaction_trigger('damage_taken', high, priority=10)
        self.battle.fire_reaction_window('damage_taken', {})
        self.assertEqual(order, ['high', 'low'])

    def test_duplicate_registration_is_noop(self):
        def h(battle, ctx):
            return None
        self.battle.register_reaction_trigger('x', h)
        self.battle.register_reaction_trigger('x', h)
        self.assertEqual(len(self.battle.reaction_handlers['x']), 1)

    def test_unregister(self):
        def h(battle, ctx):
            return [{'e': 1}]
        self.battle.register_reaction_trigger('x', h)
        self.battle.unregister_reaction_trigger('x', h)
        self.assertEqual(self.battle.fire_reaction_window('x'), [])

    def test_handler_exception_swallowed(self):
        def boom(battle, ctx):
            raise RuntimeError('nope')

        def good(battle, ctx):
            return [{'event': 'ok'}]

        self.battle.register_reaction_trigger('x', boom, priority=10)
        self.battle.register_reaction_trigger('x', good, priority=1)
        events = self.battle.fire_reaction_window('x', {})
        self.assertEqual(events, [{'event': 'ok'}])

    def test_force_miss_propagates_via_context(self):
        def force(battle, ctx):
            ctx['force_miss'] = True
            return None

        self.battle.register_reaction_trigger('attack_roll', force)
        ctx = {'force_miss': False}
        self.battle.fire_reaction_window('attack_roll', ctx)
        self.assertTrue(ctx['force_miss'])


if __name__ == '__main__':
    unittest.main()
