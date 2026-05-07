"""Phase 1 tests for the loss-of-control foundation.

Covers:
  * ``ControlOverride`` filter / force / delegate pipeline.
  * ``ControlOverrideStack`` priority + composition.
  * ``Battle.push_/pop_control_override`` + cached wrapper.
  * ``Battle.while_active`` skipping turns when an entity is
    incapacitated (without being dead/unconscious).
"""

import random
import unittest

from natural20.actions.dodge_action import DodgeAction
from natural20.battle import Battle
from natural20.controllers.control_override import (
    ControlOverride,
    ControlOverrideStack,
)
from natural20.controller import Controller
from natural20.event_manager import EventManager
from natural20.generic_controller import GenericController
from natural20.map import Map
from natural20.npc import Npc
from natural20.player_character import PlayerCharacter
from natural20.session import Session


class _StubController(Controller):
    """Records the actions it sees and always returns the first."""

    def __init__(self, session):
        super().__init__(session)
        self.last_actions = None
        self.calls = 0

    def select_action(self, battle, entity, available_actions=None):
        self.calls += 1
        self.last_actions = list(available_actions or [])
        return self.last_actions[0] if self.last_actions else None

    def move_for(self, entity, battle):
        self.calls += 1
        return None


class _DropAttacks(ControlOverride):
    CONDITION_ID = 'no_attacks'

    def filter_actions(self, entity, battle, actions):
        return [a for a in actions if getattr(a, 'action_type', None) != 'attack']


class _ForceDodge(ControlOverride):
    CONDITION_ID = 'forced_dodge'
    PRIORITY = 10

    def force_action(self, entity, battle, actions):
        return DodgeAction(self.session, entity, 'dodge')


class _BlockReactions(ControlOverride):
    CONDITION_ID = 'no_reactions'

    def block_reactions(self, entity, event):
        return True


class TestControlOverrideUnit(unittest.TestCase):
    def setUp(self):
        random.seed(1)
        self.session = Session(root_path='tests/fixtures',
                               event_manager=EventManager())
        self.base = _StubController(self.session)

    def _fake_action(self, action_type):
        class A:
            pass
        a = A()
        a.action_type = action_type
        return a

    def test_filter_runs_before_base_select(self):
        ov = _DropAttacks(self.base)
        actions = [self._fake_action('move'), self._fake_action('attack')]
        result = ov.select_action(None, None, actions)
        self.assertEqual(result.action_type, 'move')
        self.assertEqual([a.action_type for a in self.base.last_actions], ['move'])

    def test_force_action_short_circuits_base(self):
        ov = _ForceDodge(self.base)
        result = ov.select_action(None, None, [self._fake_action('move')])
        self.assertIsInstance(result, DodgeAction)
        self.assertEqual(self.base.calls, 0)

    def test_attribute_fallthrough(self):
        ov = _DropAttacks(self.base)
        # ``Controller`` instances expose ``state``; the wrapper should
        # forward to ``self.base.state`` when not set on the wrapper.
        self.base.state['foo'] = 'bar'
        self.assertEqual(ov.state['foo'], 'bar')


class TestControlOverrideStack(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures',
                               event_manager=EventManager())
        self.base = _StubController(self.session)

    def _fake_action(self, action_type):
        class A:
            pass
        a = A()
        a.action_type = action_type
        return a

    def test_filters_compose(self):
        class _DropMoves(ControlOverride):
            def filter_actions(self, entity, battle, actions):
                return [a for a in actions if a.action_type != 'move']
        stack = ControlOverrideStack(self.base, [_DropAttacks(self.base), _DropMoves(self.base)])
        actions = [self._fake_action('attack'),
                   self._fake_action('move'),
                   self._fake_action('dodge')]
        result = stack.select_action(None, None, actions)
        self.assertEqual(result.action_type, 'dodge')

    def test_higher_priority_force_wins(self):
        class _ForceMove(ControlOverride):
            PRIORITY = 1
            def force_action(self, entity, battle, actions):
                a = type('A', (), {})()
                a.action_type = 'move'
                return a
        forced_dodge = _ForceDodge(self.base)  # priority 10
        forced_move = _ForceMove(self.base)
        stack = ControlOverrideStack(self.base, [forced_move, forced_dodge])
        result = stack.select_action(None, None, [])
        self.assertIsInstance(result, DodgeAction)


class TestBattleOverrideLifecycle(unittest.TestCase):
    def setUp(self):
        random.seed(7000)
        em = EventManager()
        em.standard_cli()
        self.session = Session(root_path='tests/fixtures', event_manager=em)
        self.battle_map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.battle_map)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.skeleton = Npc.load(self.session, 'npcs/skeleton.yml')
        self.battle.add(self.fighter, 'a', controller=GenericController(self.session),
                        position='spawn_point_1')
        self.battle.add(self.skeleton, 'b', controller=GenericController(self.session),
                        position='spawn_point_3')

    def test_no_overrides_returns_base_controller(self):
        base = self.battle.controller_for(self.fighter)
        self.assertIsInstance(base, GenericController)
        self.assertEqual(self.battle.active_overrides_for(self.fighter), [])

    def test_push_wraps_controller_and_pop_restores(self):
        base = self.battle.controller_for(self.fighter)
        ov = _DropAttacks(base, source=self.skeleton, condition_id='no_attacks')
        added = self.battle.push_control_override(self.fighter, ov)
        self.assertTrue(added)

        wrapped = self.battle.controller_for(self.fighter)
        self.assertIs(wrapped, ov)
        # Calling again returns the cached wrapper instance.
        self.assertIs(self.battle.controller_for(self.fighter), wrapped)

        removed = self.battle.pop_control_override(self.fighter, condition_id='no_attacks')
        self.assertIs(removed, ov)
        self.assertIs(self.battle.controller_for(self.fighter), base)

    def test_set_controller_for_invalidates_wrapper_cache(self):
        base = self.battle.controller_for(self.fighter)
        self.battle.push_control_override(
            self.fighter,
            _DropAttacks(base, source=None, condition_id='no_attacks'),
        )
        self.assertIsNot(self.battle.controller_for(self.fighter), base)
        new_base = GenericController(self.session)
        self.battle.set_controller_for(self.fighter, new_base)
        # Wrapper is rebuilt on next access; the new wrapper points at
        # ``new_base`` (verified via the wrapper's ``base`` attribute).
        wrapped = self.battle.controller_for(self.fighter)
        self.assertIs(wrapped.base, new_base)

    def test_block_reactions_short_circuits_opportunity_attack(self):
        base = self.battle.controller_for(self.fighter)
        ov = _BlockReactions(base, condition_id='no_reactions')
        self.battle.push_control_override(self.fighter, ov)
        wrapped = self.battle.controller_for(self.fighter)
        result = wrapped.opportunity_attack_listener(
            self.battle, self.session, self.fighter, self.battle_map,
            {'target': self.skeleton},
        )
        self.assertIsNone(result)


class TestWhileActiveSkipsIncapacitated(unittest.TestCase):
    def setUp(self):
        random.seed(7000)
        em = EventManager()
        em.standard_cli()
        self.session = Session(root_path='tests/fixtures', event_manager=em)
        self.battle_map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.battle_map)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.skeleton = Npc.load(self.session, 'npcs/skeleton.yml')
        self.battle.add(self.fighter, 'a', controller=GenericController(self.session),
                        position='spawn_point_1')
        self.battle.add(self.skeleton, 'b', controller=GenericController(self.session),
                        position='spawn_point_3')
        self.battle.start()

    def test_incapacitated_entity_skips_callback(self):
        # Force the fighter into a non-unconscious incapacitated state.
        self.fighter.statuses.append('incapacitated')
        # Ensure they still register as conscious so we know the new
        # gating in ``while_active`` is what's skipping their turn.
        self.assertTrue(self.fighter.conscious())
        self.assertTrue(self.fighter.incapacitated())

        events = []
        self.session.event_manager.register_event_listener(
            'turn_skipped', lambda e: events.append(e),
        )

        callback_calls = []

        def cb(entity):
            callback_calls.append(entity)
            # Returning False lets ``while_active`` fall through to
            # ``next_turn`` so the loop terminates against ``max_rounds``.
            return False

        # Force the loop to terminate after a single round.
        self.battle.while_active(max_rounds=1, callback=cb)

        # The incapacitated fighter should never have hit the callback.
        self.assertNotIn(self.fighter, callback_calls)
        # And we should have seen at least one ``turn_skipped`` event for
        # the fighter.
        targets = [e.get('target') for e in events]
        self.assertIn(self.fighter, targets)


if __name__ == '__main__':
    unittest.main()
