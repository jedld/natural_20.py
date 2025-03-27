import unittest
from natural20.actions.help_action import HelpAction
from natural20.event_manager import EventManager
from natural20.session import Session
from natural20.map import Map
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.npc import Npc
from natural20.actions.attack_action import AttackAction
from natural20.map_renderer import MapRenderer
from natural20.die_roll import DieRoll
from natural20.utils.action_builder import autobuild
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
        self.skeleton = Npc.load(self.session, 'npcs/skeleton.yml')
        self.battle.add(self.fighter, 'a', position='spawn_point_1', token='G')
        self.battle.add(self.rogue, 'a', position='spawn_point_2', token='g')
        self.battle.add(self.skeleton, 'b', position='spawn_point_3', token='$')
        self.battle.start()
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
        action = autobuild(self.session, HelpAction, self.fighter, self.battle, match=[self.rogue])[0]
        self.battle.action(action)
        self.battle.commit(action)
        self.assertTrue(self.rogue.has_help())

    def test_help_available_actions(self):
        print(MapRenderer(self.map).render())
        self.battle.set_current_turn(self.fighter)
        available_actions = [str(a) for a in self.fighter.available_actions(self.session, self.battle)]
        self.assertIn('Help', available_actions)

    def test_advantage_on_ability_check(self):
        print(MapRenderer(self.map).render())
        action = autobuild(self.session, HelpAction, self.fighter, self.battle, match=[self.rogue])[0]
        self.rogue.stealth_check(self.battle)
        print(DieRoll.last_roll())
        self.assertEqual(DieRoll.last_roll().advantage, False)
        self.battle.action(action)
        self.battle.commit(action)
        self.assertTrue(self.rogue.has_help())
        self.rogue.stealth_check(self.battle)
        print(DieRoll.last_roll())
        self.assertEqual(DieRoll.last_roll().advantage, True)
        self.rogue.stealth_check(self.battle)
        print(DieRoll.last_roll())
        self.assertEqual(DieRoll.last_roll().advantage, False)

    def test_advantage_on_attack_rolls(self):
        self.map.move_to(self.fighter, 2, 1, self.battle)
        self.skeleton.set_hp(100, override_max=True)
        print(MapRenderer(self.map).render())
        help_action = autobuild(self.session, HelpAction, self.rogue, self.battle, match=[self.skeleton])[0]
        attack_roll = autobuild(self.session, AttackAction, self.fighter, self.battle, match=[self.skeleton, 'vicious_rapier'])[0]
        
        self.battle.action(attack_roll)
        self.battle.commit(attack_roll)
        self.assertEqual(DieRoll.last_roll().advantage, False)

        # let the rogue distract the skeleton
        self.battle.action(help_action)
        self.battle.commit(help_action)
        attack_roll = autobuild(self.session, AttackAction, self.fighter, self.battle, match=[self.skeleton, 'vicious_rapier'])[0]
        self.battle.action(attack_roll)
        self.battle.commit(attack_roll)
        self.assertEqual(DieRoll.last_roll().advantage, True)

        self.fighter.reset_turn(self.battle)# should expire after use
        attack_roll = autobuild(self.session, AttackAction, self.fighter, self.battle, match=[self.skeleton, 'vicious_rapier'])[0]
        self.battle.action(attack_roll)
        self.battle.commit(attack_roll)
        self.assertEqual(DieRoll.last_roll().advantage, False)
