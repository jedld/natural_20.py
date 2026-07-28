"""Tests for natural20/actions/pickpocket_action.py – D&D 5e (2014) pickpocket."""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from natural20.actions.pickpocket_action import (
    PickpocketAction,
    PickpocketBonusAction,
    _is_pc,
    _pickpocket_pc_to_pc_allowed,
)
from natural20.event_manager import EventManager
from natural20.session import Session
from natural20.map import Map
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
import random


class _MakeSession:
    """Mixin to provide session/map/battle setup."""

    def _make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        random.seed(7000)
        self.session = Session(root_path='tests/fixtures', event_manager=event_manager)

    def _make_battle(self):
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)


class TestPickpocketActionBasic(_MakeSession, unittest.TestCase):
    """Basic unit tests for PickpocketAction."""

    def setUp(self):
        self._make_session()
        self.npc = self.session.npc('goblin')
        self.npc2 = self.session.npc('goblin')

    def test_action_type(self):
        action = PickpocketAction(self.session, self.npc, 'pickpocket')
        self.assertEqual(action.action_type, 'pickpocket')

    def test_str(self):
        action = PickpocketAction(self.session, self.npc, 'pickpocket')
        self.assertEqual(str(action), "Pickpocket")

    def test_clone(self):
        action = PickpocketAction(self.session, self.npc, 'pickpocket')
        action.target = self.npc2
        action.item_name = "copper coin"
        cloned = action.clone()
        self.assertEqual(cloned.target, self.npc2)
        self.assertEqual(cloned.item_name, "copper coin")


class TestPickpocketCan(_MakeSession, unittest.TestCase):
    """Test the can() static method."""

    def setUp(self):
        self._make_session()
        self.npc = self.session.npc('goblin')

    def test_out_of_combat(self):
        # Out of combat, can() returns True by default
        self.assertTrue(PickpocketAction.can(self.npc, None))

    def test_no_action_available(self):
        battle = MagicMock()
        with unittest.mock.patch.object(self.npc, 'total_actions', return_value=0):
            self.assertFalse(PickpocketAction.can(self.npc, battle))

    def test_action_available(self):
        battle = MagicMock()
        with unittest.mock.patch.object(self.npc, 'total_actions', return_value=1):
            self.assertTrue(PickpocketAction.can(self.npc, battle))

    def test_pc_to_pc_blocked_in_battle(self):
        """When PC-to-PC is disabled, can() returns False for PCs in battle."""
        battle = MagicMock()
        battle.total_actions.return_value = 1
        pc = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        with MagicMock() as mock_allowed:
            mock_allowed.return_value = False
            with unittest.mock.patch(
                'natural20.actions.pickpocket_action._pickpocket_pc_to_pc_allowed',
                return_value=False
            ):
                with unittest.mock.patch('natural20.actions.pickpocket_action._is_pc', return_value=True):
                    self.assertFalse(PickpocketAction.can(pc, battle))


class TestPickpocketRangeCheck(_MakeSession, unittest.TestCase):
    """Test range validation (must be within 5 feet = adjacent)."""

    def setUp(self):
        self._make_session()
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.source = self.session.npc('goblin')
        self.target = self.session.npc('goblin')
        self.map.place((1, 1), self.source)
        self.map.place((1, 2), self.target)

    def test_resolve_adjacent(self):
        action = PickpocketAction(self.session, self.source, 'pickpocket')
        action.target = self.target
        attempt = action.roll_pickpocket_attempt(self.session, self.map, self.battle)
        # Should not be a range error (may succeed or fail on skill check)
        self.assertNotEqual(attempt.get('reason'), 'target_out_of_range')

    def test_resolve_too_far(self):
        # Move target to (3, 3) -- more than 5 feet away (Chebyshev distance > 1)
        self.map.move_to(self.target, 3, 3, self.battle)
        action = PickpocketAction(self.session, self.source, 'pickpocket')
        action.target = self.target
        attempt = action.roll_pickpocket_attempt(self.session, self.map, self.battle)
        self.assertEqual(attempt.get('reason'), 'target_out_of_range')
        self.assertFalse(attempt.get('success'))

    def test_resolve_diagonal_adjacent(self):
        # Place target diagonally adjacent at (2, 2)
        self.map.move_to(self.target, 2, 2, self.battle)
        action = PickpocketAction(self.session, self.source, 'pickpocket')
        action.target = self.target
        attempt = action.roll_pickpocket_attempt(self.session, self.map, self.battle)
        # Diagonal adjacency (Chebyshev distance == 1) should be valid
        self.assertNotEqual(attempt.get('reason'), 'target_out_of_range')


class TestPickpocketPCtoPCBlocking(_MakeSession, unittest.TestCase):
    """Test campaign-level PC-to-PC pickpocket blocking."""

    def setUp(self):
        self._make_session()

    def test_pc_to_pc_allowed_default(self):
        """When campaign has no setting, PC-to-PC is allowed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = os.path.join(tmpdir, 'index.json')
            with open(index_path, 'w') as f:
                json.dump({}, f)
            session = MagicMock(root_path=tmpdir)
            self.assertTrue(_pickpocket_pc_to_pc_allowed(session))

    def test_pc_to_pc_disabled(self):
        """When campaign sets allow_pc_to_pc: false, PC-to-PC is blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = os.path.join(tmpdir, 'index.json')
            with open(index_path, 'w') as f:
                json.dump({"pickpocket": {"allow_pc_to_pc": False}}, f)
            session = MagicMock(root_path=tmpdir)
            self.assertFalse(_pickpocket_pc_to_pc_allowed(session))

    def test_pc_to_pc_disabled_backwards_compat(self):
        """Backwards compat: pickpocket_allow_pc_to_pc: false blocks PC-to-PC."""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = os.path.join(tmpdir, 'index.json')
            with open(index_path, 'w') as f:
                json.dump({"pickpocket_allow_pc_to_pc": False}, f)
            session = MagicMock(root_path=tmpdir)
            self.assertFalse(_pickpocket_pc_to_pc_allowed(session))

    def test_is_pc_helper_with_pc(self):
        """Test the _is_pc helper function with a PC."""
        pc = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.assertTrue(_is_pc(pc))

    def test_is_pc_helper_with_npc(self):
        """Test the _is_pc helper function with an NPC."""
        goblin = self.session.npc('goblin')
        self.assertFalse(_is_pc(goblin))

    def test_is_pc_helper_with_none(self):
        """Test the _is_pc helper function with None."""
        self.assertFalse(_is_pc(None))


class TestPickpocketResolveAndApply(_MakeSession, unittest.TestCase):
    """Test resolve() and apply() methods."""

    def setUp(self):
        self._make_session()
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.source = self.session.npc('goblin')
        self.target = self.session.npc('goblin')
        self.map.place((1, 1), self.source)
        self.map.place((1, 2), self.target)
        self.battle.add(self.source, 'a')

    def test_resolve_missing_target(self):
        action = PickpocketAction(self.session, self.source, 'pickpocket')
        action.item_name = "copper coin"
        with self.assertRaises(Exception):
            action.resolve(self.session, self.map, {'battle': self.battle})

    def test_resolve_missing_item_name(self):
        action = PickpocketAction(self.session, self.source, 'pickpocket')
        action.target = self.target
        with self.assertRaises(Exception):
            action.resolve(self.session, self.map, {'battle': self.battle})

    def test_validate_missing_target(self):
        action = PickpocketAction(self.session, self.source, 'pickpocket')
        action.item_name = "copper coin"
        errors = action.validate(self.map)
        self.assertTrue(any("target" in e for e in errors))

    def test_validate_missing_item_name(self):
        action = PickpocketAction(self.session, self.source, 'pickpocket')
        action.target = self.target
        errors = action.validate(self.map)
        self.assertTrue(any("item_name" in e for e in errors))

    def test_apply_success_transfers_item(self):
        self.target.add_item('arrows', 5)
        before_target = self.target.inventory['arrows']['qty']
        before_source = self.source.inventory.get('arrows', {}).get('qty', 0)
        item = {
            'type': 'pickpocket',
            'source': self.source,
            'target': self.target,
            'success': True,
            'item_name': 'arrows',
            'battle': self.battle,
        }
        PickpocketAction.apply(self.battle, item, session=self.session)
        self.assertEqual(self.target.inventory['arrows']['qty'], before_target - 1)
        self.assertEqual(self.source.inventory['arrows']['qty'], before_source + 1)

    def test_apply_success(self):
        """Test that apply() logs a successful pickpocket."""
        item = {
            'type': 'pickpocket',
            'source': self.source,
            'target': self.target,
            'success': True,
            'item_name': 'arrows',
            'battle': self.battle,
        }
        # Should not raise
        PickpocketAction.apply(self.battle, item, session=self.session)

    def test_apply_failure(self):
        """Test that apply() logs a failed pickpocket."""
        item = {
            'type': 'pickpocket',
            'source': self.source,
            'target': self.target,
            'success': False,
            'item_name': 'arrows',
            'battle': self.battle,
            'reason': 'detection',
        }
        # Should not raise
        PickpocketAction.apply(self.battle, item, session=self.session)

    def test_apply_wrong_type(self):
        """Test that apply() ignores non-pickpocket items."""
        item = {'type': 'attack'}
        # Should not raise
        PickpocketAction.apply(self.battle, item, session=self.session)

    def test_apply_consumes_action(self):
        """Test that apply() consumes the action from battle."""
        self.battle.entities[self.source]['action'] = 1
        item = {
            'type': 'pickpocket',
            'source': self.source,
            'target': self.target,
            'success': True,
            'item_name': 'arrows',
            'battle': self.battle,
        }
        PickpocketAction.apply(self.battle, item, session=self.session)
        # Action should be consumed
        self.assertEqual(self.battle.entities[self.source]['action'], 0)


class TestPickpocketCombatLog(_MakeSession, unittest.TestCase):
    """Pickpocket events should appear in the combat log via EventManager."""

    def setUp(self):
        self._make_session()
        self.logged = []

        class _CaptureLogger:
            def log(self, event_msg, event=None, visibility=None):
                self.entries = self.entries if hasattr(self, 'entries') else []
                self.entries.append(event_msg)

        self.output_logger = _CaptureLogger()
        self.output_logger.entries = []
        self.session.event_manager = EventManager(output_logger=self.output_logger)
        self.session.event_manager.standard_cli()
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.source = self.session.npc('goblin')
        self.target = self.session.npc('goblin')
        self.map.place((1, 1), self.source)
        self.map.place((1, 2), self.target)

    def test_success_logs_to_combat_log(self):
        self.target.add_item('arrows', 3)
        action = PickpocketAction(self.session, self.source, 'pickpocket')
        action.target = self.target
        action.item_name = 'arrows'
        action.pickpocket_attempt = {
            'success': True,
            'roll_total': 20,
            'passive_insight': 10,
        }
        action.resolve(self.session, self.map, {'battle': self.battle})
        PickpocketAction.apply(self.battle, action.result[0], session=self.session)
        self.assertTrue(self.output_logger.entries)
        self.assertIn('pickpockets', self.output_logger.entries[-1])
        self.assertIn('Arrows', self.output_logger.entries[-1])
        self.assertIn('Sleight of Hand 20', self.output_logger.entries[-1])
        self.assertIn('passive Insight 10', self.output_logger.entries[-1])

    def test_detection_failure_logs_roll_total_to_combat_log(self):
        action = PickpocketAction(self.session, self.source, 'pickpocket')
        action.target = self.target
        action.pickpocket_attempt = {
            'success': False,
            'roll_total': 3,
            'passive_insight': 15,
            'reason': 'detection',
            'message': f"{self.source.name}'s pickpocket attempt on {self.target.name} fails.",
        }
        action.resolve(self.session, self.map, {'battle': self.battle})
        PickpocketAction.apply(self.battle, action.result[0], session=self.session)
        self.assertIn('Sleight of Hand 3', self.output_logger.entries[-1])
        self.assertIn('passive Insight 15', self.output_logger.entries[-1])

    def test_detection_failure_logs_to_combat_log(self):
        action = PickpocketAction(self.session, self.source, 'pickpocket')
        action.target = self.target
        action.pickpocket_attempt = {
            'success': False,
            'roll_total': 3,
            'passive_insight': 15,
            'reason': 'detection',
            'message': f"{self.source.name}'s pickpocket attempt on {self.target.name} fails.",
        }
        action.resolve(self.session, self.map, {'battle': self.battle})
        PickpocketAction.apply(self.battle, action.result[0], session=self.session)
        self.assertTrue(self.output_logger.entries)
        self.assertIn('caught trying to pickpocket', self.output_logger.entries[-1])


class TestPickpocketBonusAction(_MakeSession, unittest.TestCase):
    """Test PickpocketBonusAction (Thief Rogue Fast Hands)."""

    def setUp(self):
        self._make_session()
        self.npc = self.session.npc('goblin')

    def test_bonus_action_type(self):
        action = PickpocketBonusAction(self.session, self.npc, 'pickpocket')
        self.assertTrue(action.as_bonus_action)

    def test_bonus_action_can_false_without_bonus(self):
        battle = MagicMock()
        self.npc.total_bonus_actions = MagicMock(return_value=0)
        self.assertFalse(PickpocketBonusAction.can(self.npc, battle))

    def test_bonus_action_can_false_without_fast_hands(self):
        """NPC without Fast Hands feature can't use bonus action pickpocket."""
        battle = MagicMock()
        self.npc.class_feature = MagicMock(return_value=None)
        self.npc.total_bonus_actions = MagicMock(return_value=1)
        self.assertFalse(PickpocketBonusAction.can(self.npc, battle))


class TestPickpocketBuildMap(_MakeSession, unittest.TestCase):
    """Test build_map() returns correct UI config."""

    def setUp(self):
        self._make_session()
        self.npc = self.session.npc('goblin')

    def test_build_map_structure(self):
        action = PickpocketAction(self.session, self.npc, 'pickpocket')
        config = action.build_map()
        self.assertIn('action', config)
        self.assertIn('param', config)
        self.assertIn('next', config)
        params = config['param']
        self.assertEqual(len(params), 1)
        self.assertEqual(params[0]['type'], 'select_target')
        self.assertEqual(params[0]['range'], 5)

    def test_build_map_attempt_step_after_target(self):
        action = PickpocketAction(self.session, self.npc, 'pickpocket')
        target = self.session.npc('goblin')
        inner = action.build_map()['next'](target)
        self.assertEqual(inner['param'][0]['type'], 'pickpocket_attempt')
        attempt = {
            'success': True,
            'roll_total': 18,
            'passive_insight': 11,
            'message': 'success',
        }
        item_step = inner['next'](attempt)
        self.assertEqual(item_step['param'][0]['type'], 'select_pickpocket_item')
        finished = item_step['next']('arrows')
        self.assertEqual(finished.item_name, 'arrows')
        self.assertEqual(finished.target, target)
        self.assertTrue(finished.pickpocket_attempt.get('success'))

    def test_build_static_method(self):
        """Test the static build() method."""
        config = PickpocketAction.build(self.session, self.npc)
        self.assertIn('action', config)
        self.assertIn('param', config)


class TestPickpocketPCtoPCInResolve(_MakeSession, unittest.TestCase):
    """Test PC-to-PC blocking during resolve()."""

    def setUp(self):
        self._make_session()
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.pc = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.npc = self.session.npc('goblin')
        self.map.move_to(self.pc, 1, 1, self.battle)
        self.map.move_to(self.npc, 1, 2, self.battle)

    def test_pc_to_npc_allowed(self):
        """PC-to-NPC pickpocket should be allowed by default."""
        with unittest.mock.patch(
            'natural20.actions.pickpocket_action._pickpocket_pc_to_pc_allowed',
            return_value=True
        ):
            action = PickpocketAction(self.session, self.pc, 'pickpocket')
            action.target = self.npc
            action.item_name = "copper coin"
            action.pickpocket_attempt = {
                'success': True,
                'roll_total': 20,
                'passive_insight': 10,
            }
            action.resolve(self.session, self.map, {'battle': self.battle})
            # Should not be blocked
            result = action.result[0]
            self.assertNotEqual(result.get('reason'), 'pc_to_pc_disabled')

    def test_pc_to_pc_disabled_during_resolve(self):
        """PC-to-PC pickpocket should be blocked during resolve when disabled."""
        # Create another PC as target
        pc2 = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        pc2.name = "PC2"
        self.map.move_to(pc2, 1, 2, self.battle)
        with unittest.mock.patch(
            'natural20.actions.pickpocket_action._pickpocket_pc_to_pc_allowed',
            return_value=False
        ):
            with unittest.mock.patch(
                'natural20.actions.pickpocket_action._is_pc',
                return_value=True
            ):
                action = PickpocketAction(self.session, self.pc, 'pickpocket')
                action.target = pc2
                attempt = action.roll_pickpocket_attempt(self.session, self.map, self.battle)
                self.assertEqual(attempt.get('reason'), 'pc_to_pc_disabled')
                self.assertFalse(attempt.get('success'))


if __name__ == '__main__':
    unittest.main()
