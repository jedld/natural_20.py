from natural20.event_manager import EventManager
import random
from natural20.session import Session
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.actions.hide_action import HideAction
from natural20.map import Map
from natural20.map_renderer import MapRenderer
import os
import unittest

class TestHideAction(unittest.TestCase):

    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        random.seed(7000)
        return Session(root_path='tests/fixtures', event_manager=event_manager)
    
    def setUp(self):
        self.session = self.make_session()
        self.battle = Battle(self.session, None)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.npc = self.session.npc('goblin')
        self.battle.add(self.fighter, 'a')
        self.battle.add(self.npc, 'b')
        self.npc.reset_turn(self.battle)
        self.fighter.reset_turn(self.battle)


    def test_auto_build(self):
        self.assertTrue(not self.npc.hidden())
        hide_action = HideAction.build(self.session, self.npc)
        hide_action.resolve(self.session, None, { "battle" :self.battle})
        self.battle.commit(hide_action)
        self.assertTrue(self.npc.hidden())

    def test_hiding_in_terrain(self):
        battle_map = Map(self.session, 'hide_test')
        battle = Battle(self.session, battle_map)
        character = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        npc = self.session.npc('goblin')
        battle.add(character, 'a', position='spawn_point_2')
        battle.add(npc, 'b', position='spawn_point_1')
        print(MapRenderer(battle_map).render(line_of_sight=character))
        npc.do_hide(20)
        self.assertTrue(npc.hidden())
        print(MapRenderer(battle_map, battle).render(line_of_sight=character))

    def test_pc_can_hide_out_of_combat(self):
        battle_map = Map(self.session, 'hide_test')
        battle = Battle(self.session, battle_map)
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        battle.add(fighter, 'a', position='spawn_point_2')

        available_actions = fighter.available_actions(self.session, None, map=battle_map)
        hide_actions = [action for action in available_actions if isinstance(action, HideAction)]

        self.assertEqual(len(hide_actions), 1)

        hide_action = hide_actions[0]
        hide_action.resolve(self.session, battle_map, {'battle': None})
        HideAction.apply(None, hide_action.result[0], session=self.session)

        self.assertTrue(fighter.hidden())
