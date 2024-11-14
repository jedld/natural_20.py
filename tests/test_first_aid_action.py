import unittest
from natural20.actions.first_aid_action import FirstAidAction
from natural20.event_manager import EventManager
from natural20.session import Session
from natural20.map import Map
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.map_renderer import MapRenderer
import random

class TestFirstAidAction(unittest.TestCase):
    def setUp(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        random.seed(7000)
        self.session = Session(root_path='tests/fixtures', event_manager=event_manager)
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.rogue = PlayerCharacter.load(self.session, 'halfling_rogue.yml')
        self.battle.add(self.fighter, 'a', position='spawn_point_1', token='G')
        self.battle.add(self.rogue, 'b', position='spawn_point_2', token='g')
        self.rogue.reset_turn(self.battle)
        self.fighter.reset_turn(self.battle)
        self.map.move_to(self.fighter, 1, 2, self.battle)
        self.map.move_to(self.rogue, 1, 1, self.battle)
        self.rogue.make_unconscious()

    def test_can(self):
        print(MapRenderer(self.map).render())
        self.assertTrue(FirstAidAction.can(self.fighter, self.battle))

    def test_perform_first_aid(self):
        print(MapRenderer(self.map).render())
        self.assertFalse(self.rogue.stable())
        action = FirstAidAction.build(self.session, self.fighter)['next'](self.rogue)
        random.seed(1000)
        self.battle.action(action)
        self.battle.commit(action)
        self.assertTrue(self.rogue.stable())

if __name__ == '__main__':
    unittest.main()
