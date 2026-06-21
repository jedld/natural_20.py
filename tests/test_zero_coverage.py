"""Tests for previously untested modules (0% coverage targets)."""
import unittest
from unittest.mock import MagicMock

from natural20.agent import Agent
from natural20.actions.inventory_action import InventoryAction
from natural20.event_manager import EventManager
from natural20.session import Session
from natural20.map import Map
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter


class TestAgent(unittest.TestCase):
    """Tests for natural20/agent.py — basic stub class."""

    def test_instantiate_agent(self):
        agent = Agent(name="TestAgent", level=5)
        self.assertEqual(agent.name, "TestAgent")
        self.assertEqual(agent.level, 5)

    def test_process_turn_is_stub(self):
        agent = Agent(name="TestAgent", level=1)
        # process_turn is a stub method (note: signature missing 'self' in source)
        # Call as unbound since the method definition lacks self parameter
        result = Agent.process_turn([])
        self.assertIsNone(result)


class TestInventoryAction(unittest.TestCase):
    """Tests for natural20/actions/inventory_action.py."""

    def setUp(self):
        self.event_manager = EventManager()
        self.session = Session(root_path='tests/fixtures', event_manager=self.event_manager)
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.entity = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(self.entity, 'a', position='spawn_point_1', token='G')
        self.entity.reset_turn(self.battle)

    def test_can_always_returns_true(self):
        # InventoryAction.can() should always return True
        self.assertTrue(InventoryAction.can(self.entity, self.battle))
        self.assertTrue(InventoryAction.can(self.entity, None))

    def test_build_map_returns_show_inventory(self):
        # InventoryAction is a @dataclass which overrides Action.__init__,
        # so we instantiate directly and test build_map
        action = InventoryAction()
        result = action.build_map()
        self.assertEqual(result['action'], action)
        self.assertIn('param', result)
        # First param should be the show_inventory selector
        self.assertEqual(result['param'][0]['type'], 'show_inventory')

    def test_has_next_callback(self):
        action = InventoryAction()
        result = action.build_map()
        self.assertIn('next', result)
        # next should be callable
        self.assertTrue(callable(result['next']))


class TestNoteObject(unittest.TestCase):
    """Tests for natural20/item_library/note.py."""

    def setUp(self):
        self.event_manager = EventManager()
        self.session = Session(root_path='tests/fixtures', event_manager=self.event_manager)
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.entity = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(self.entity, 'a', position='spawn_point_1', token='G')
        self.entity.reset_turn(self.battle)

    def test_note_instantiation(self):
        from natural20.item_library.note import Note
        props = {
            'name': 'Test Note',
            'x': 5,
            'y': 5,
            'note_text': 'Hello world',
        }
        note = Note(self.session, self.map, props)
        self.assertEqual(note.properties['name'], 'Test Note')
        self.assertEqual(note.properties['note_text'], 'Hello world')

    def test_note_build_map_delegates_to_parent(self):
        from natural20.item_library.note import Note
        props = {
            'name': 'Test Note',
            'x': 5,
            'y': 5,
            'note_text': 'Hello world',
        }
        note = Note(self.session, self.map, props)
        # build_map delegates to Object.build_map() which returns None for non-loot actions
        mock_action = MagicMock()
        mock_action_object = MagicMock()
        result = note.build_map(mock_action, mock_action_object)
        # When action != 'loot', Object.build_map() returns None
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
