import unittest
from natural20.actions.help_action import HelpAction
from natural20.event_manager import EventManager
from natural20.session import Session
from natural20.map import Map
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.map_renderer import MapRenderer
import random

class TestHelpAction(unittest.TestCase):
    def setUp(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        random.seed(7000)
        self.session = Session(root_path='tests/fixtures', event_manager=event_manager)
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.rogue = PlayerCharacter.load(self.session, 'halfling_rogue.yml')
        self.battle.add(self.fighter, 'a', position='spawn_point_1', token='G')
        self.battle.add(self.rogue, 'b', position='spawn_point_2', token='g')
        self.rogue.reset_turn(self.battle)
        self.fighter.reset_turn(self.battle)
        self.map.move_to(self.fighter, 1, 2, self.battle)
        self.map.move_to(self.rogue, 1, 1, self.battle)

    def test_can(self):
        print(MapRenderer(self.map).render())
        self.assertTrue(HelpAction.can(self.fighter, self.battle))

    def test_help_action(self):
        print(MapRenderer(self.map).render())
        # Create and resolve help action
        action = HelpAction.build(self.session, self.fighter)['next'](self.rogue)
        self.battle.action(action)
        self.battle.commit(action)
        
        # Verify the help effect was applied
        self.assertEqual(self.battle.entity_state_for(self.rogue).get('target_effect', {}).get('help'), True)
        
        # Verify action was consumed
        self.assertEqual(self.battle.entity_state_for(self.fighter)['action'], 0)

    def test_help_range(self):
        # Move rogue out of range
        self.map.move_to(self.rogue, 3, 3, self.battle)
        print(MapRenderer(self.map).render())
        
        # Try to help out of range target
        action = HelpAction.build(self.session, self.fighter)['next'](self.rogue)
        self.assertIsNone(action)  # Should not be able to help target out of range

    def test_help_available_actions(self):
        print(MapRenderer(self.map).render())
        available_actions = [str(a) for a in self.fighter.available_actions(self.session, self.battle)]
        self.assertIn('Help', available_actions) 