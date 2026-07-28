"""Tests for natural20/utils/pickpocket_detection.py – NPC pickpocket witness detection."""

import unittest
from unittest.mock import MagicMock

from natural20.utils.pickpocket_detection import (
    _check_npc_detection,
    _resolve_sleight_of_hand_dc,
    _entity_uid,
    collect_witness_npcs,
    evaluate_pickpocket_detection,
    sleight_of_hand_total_from_roll,
)
from natural20.event_manager import EventManager
from natural20.session import Session
from natural20.map import Map
from natural20.battle import Battle
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


class TestEntityUid(_MakeSession, unittest.TestCase):
    """Test _entity_uid helper."""

    def test_none(self):
        self.assertIsNone(_entity_uid(None))

    def test_with_uid(self):
        entity = MagicMock()
        entity.entity_uid = 'npc_goblin_001'
        self.assertEqual(_entity_uid(entity), 'npc_goblin_001')

    def test_without_uid(self):
        entity = MagicMock()
        del entity.entity_uid
        self.assertIsNone(_entity_uid(entity))


class TestSleightOfHandDC(_MakeSession, unittest.TestCase):
    """Test Sleight of Hand DC helpers for witness detection."""

    def test_resolve_sleight_of_hand_dc(self):
        self.assertEqual(_resolve_sleight_of_hand_dc(18), 18)
        self.assertIsNone(_resolve_sleight_of_hand_dc(None))

    def test_sleight_of_hand_total_from_roll(self):
        roll = MagicMock()
        roll.result.return_value = 18
        self.assertEqual(sleight_of_hand_total_from_roll(roll), 18)
        self.assertEqual(sleight_of_hand_total_from_roll(12), 12)


class TestCheckNpcDetection(_MakeSession, unittest.TestCase):
    """Test _check_npc_detection for vision-based detection."""

    def setUp(self):
        self._make_session()
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)

        # Create source (pickpocketer), target, and witness NPC
        self.source = self.session.npc('goblin')
        self.target = self.session.npc('goblin')
        self.witness = self.session.npc('goblin')

        # Place them on the map
        self.map.move_to(self.source, 1, 1, self.battle)
        self.map.move_to(self.target, 1, 2, self.battle)
        self.map.move_to(self.witness, 1, 3, self.battle)

    def test_missing_map(self):
        result = _check_npc_detection(
            self.source, self.source, self.target, None, success=False
        )
        self.assertFalse(result['noticed'])
        self.assertEqual(result['reason'], 'missing_entity_or_map')

    def test_npc_cannot_see(self):
        """When NPC cannot see the pickpocketer, they should not notice."""
        result = _check_npc_detection(
            self.witness, self.source, self.target, self.map,
            battle=self.battle, success=False, sleight_of_hand_total=18,
        )
        self.assertIn('noticed', result)
        self.assertIn('detection_type', result)
        self.assertIn('npc_passive_perception', result)
        self.assertIn('pickpocketer_sleight_of_hand_dc', result)
        self.assertEqual(result['pickpocketer_sleight_of_hand_dc'], 18)

    def test_witness_notices_when_pp_meets_sleight_of_hand(self):
        with unittest.mock.patch(
            'natural20.utils.pickpocket_detection.passive_perception_for',
            return_value=18,
        ), unittest.mock.patch.object(
            self.map, 'can_see', return_value=True,
        ):
            result = _check_npc_detection(
                self.witness, self.source, self.target, self.map,
                sleight_of_hand_total=18,
            )
        self.assertTrue(result['noticed'])
        self.assertEqual(result['detection_type'], 'passive_perception')

    def test_witness_misses_when_pp_below_sleight_of_hand(self):
        with unittest.mock.patch(
            'natural20.utils.pickpocket_detection.passive_perception_for',
            return_value=12,
        ), unittest.mock.patch.object(
            self.map, 'can_see', return_value=True,
        ):
            result = _check_npc_detection(
                self.witness, self.source, self.target, self.map,
                sleight_of_hand_total=18,
            )
        self.assertFalse(result['noticed'])
        self.assertEqual(result['detection_type'], 'unaware')


class TestEvaluatePickpocketDetection(_MakeSession, unittest.TestCase):
    """Test evaluate_pickpocket_detection main entry point."""

    def setUp(self):
        self._make_session()
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)

        self.source = self.session.npc('goblin')
        self.target = self.session.npc('goblin')
        self.witness = self.session.npc('goblin')

        self.map.move_to(self.source, 1, 1, self.battle)
        self.map.move_to(self.target, 1, 2, self.battle)
        self.map.move_to(self.witness, 1, 3, self.battle)

    def test_none_pickpocketer(self):
        results = evaluate_pickpocket_detection(self.session, None, self.target)
        self.assertEqual(results, [])

    def test_none_session(self):
        results = evaluate_pickpocket_detection(None, self.source, self.target)
        self.assertEqual(results, [])

    def test_skip_detection(self):
        results = evaluate_pickpocket_detection(
            self.session, self.source, self.target,
            battle=self.battle, battle_map=self.map,
            _skip_detection=True
        )
        self.assertEqual(results, [])

    def test_returns_detection_dicts(self):
        """Should return a list of detection results."""
        results = evaluate_pickpocket_detection(
            self.session, self.source, self.target,
            battle=self.battle, battle_map=self.map,
            success=False,
            sleight_of_hand_total=15,
        )
        self.assertIsInstance(results, list)
        for r in results:
            self.assertIn('npc', r)
            self.assertIn('noticed', r)
            self.assertIn('detection_type', r)


class TestCollectWitnessNpcs(_MakeSession, unittest.TestCase):
    """Test collect_witness_npcs (no stealth checks)."""

    def setUp(self):
        self._make_session()
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)

        self.source = self.session.npc('goblin')
        self.target = self.session.npc('goblin')
        self.witness = self.session.npc('goblin')

        self.map.move_to(self.source, 1, 1, self.battle)
        self.map.move_to(self.target, 1, 2, self.battle)
        self.map.move_to(self.witness, 1, 3, self.battle)

    def test_none_pickpocketer(self):
        results = collect_witness_npcs(self.source, self.target, None)
        self.assertEqual(results, [])

    def test_returns_witness_dicts(self):
        results = collect_witness_npcs(
            self.source, self.target, self.session,
            battle=self.battle, battle_map=self.map
        )
        self.assertIsInstance(results, list)
        for r in results:
            self.assertIn('npc', r)
            self.assertIn('can_see', r)
            self.assertIn('can_hear', r)
