"""Tests for Roll Initiative validation (opposing groups check).

Ensures that starting a battle requires at least one opposing entity group
to prevent accidental "friendly-only" combats.
"""
import sys
import os
import unittest

# Ensure the webapp path is importable for the blueprint function
_webapp_path = os.path.join(os.path.dirname(__file__), '..', 'n20-webapp', 'webapp')
if _webapp_path not in sys.path:
    sys.path.insert(0, _webapp_path)

from natural20.battle import Battle, build_opposing_groups
from natural20.map import Map
from natural20.session import Session
from natural20.player_character import PlayerCharacter
from natural20.event_manager import EventManager


def _make_session():
    """Create a minimal test session with event manager."""
    event_manager = EventManager()
    event_manager.standard_cli()
    return Session(root_path='tests/fixtures', event_manager=event_manager)


class TestRollInitiativeValidation(unittest.TestCase):
    """Tests for the Roll Initiative validation logic."""

    def test_battle_opponents_of_standard_factions(self):
        """Standard factions (a vs b) should yield opponents."""
        session = _make_session()
        battle_map = Map(session, 'tests/fixtures/battle_sim_objects')
        battle = Battle(session, battle_map)

        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        npc = session.npc('goblin', {"name": 'enemy'})

        battle.add(fighter, 'a')
        battle.add(npc, 'b')

        # Fighter should have the goblin as an opponent
        opponents = battle.opponents_of(fighter)
        self.assertIn(npc, opponents)

        # Goblin should have the fighter as an opponent
        opponents = battle.opponents_of(npc)
        self.assertIn(fighter, opponents)

    def test_battle_same_group_no_opponents(self):
        """Same group entities should not have opponents."""
        session = _make_session()
        battle_map = Map(session, 'tests/fixtures/battle_sim_objects')
        battle = Battle(session, battle_map)

        fighter1 = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        fighter2 = PlayerCharacter.load(session, 'high_elf_mage.yml')

        battle.add(fighter1, 'a')
        battle.add(fighter2, 'a')

        # Same group — no opponents
        opponents = battle.opponents_of(fighter1)
        self.assertEqual(opponents, [])

    def test_battle_opposing_groups_default(self):
        """build_opposing_groups should derive groups from session config."""
        session = _make_session()
        opposing = build_opposing_groups(session)
        # Default fallback should provide at least 'a' and 'b'
        self.assertIn('a', opposing)
        self.assertIn('b', opposing)


class TestValidateOpposingGroupsFunction(unittest.TestCase):
    """Tests for the _validate_opposing_groups helper."""

    def test_validate_raises_when_no_opponents(self):
        """_validate_opposing_groups should raise when no opposing groups exist."""
        from blueprints.battle import _validate_opposing_groups

        session = _make_session()
        battle_map = Map(session, 'tests/fixtures/battle_sim_objects')
        battle = Battle(session, battle_map)

        fighter1 = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        fighter2 = PlayerCharacter.load(session, 'high_elf_mage.yml')

        battle.add(fighter1, 'a')
        battle.add(fighter2, 'a')
        battle.start()

        with self.assertRaises(ValueError) as context:
            _validate_opposing_groups(battle)

        self.assertIn("opposing entity group", str(context.exception))

    def test_validate_passes_when_opponents_exist(self):
        """_validate_opposing_groups should pass when at least one opponent exists."""
        from blueprints.battle import _validate_opposing_groups

        session = _make_session()
        battle_map = Map(session, 'tests/fixtures/battle_sim_objects')
        battle = Battle(session, battle_map)

        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        npc = session.npc('goblin', {"name": 'enemy'})

        battle.add(fighter, 'a')
        battle.add(npc, 'b')
        battle.start()

        # Should not raise
        _validate_opposing_groups(battle)


if __name__ == '__main__':
    unittest.main()
