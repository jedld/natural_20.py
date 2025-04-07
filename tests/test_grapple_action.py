import unittest
from natural20.actions.grapple_action import GrappleAction
from natural20.actions.escape_grapple_action import EscapeGrappleAction
from natural20.actions.move_action import MoveAction
from natural20.event_manager import EventManager
from natural20.session import Session
from natural20.map import Map
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.map_renderer import MapRenderer
import random

class TestGrappleAction(unittest.TestCase):
    def setUp(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        random.seed(7000)
        self.session = Session(root_path='tests/fixtures', event_manager=event_manager)
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.npc = self.session.npc('goblin')
        self.battle.add(self.fighter, 'a', position='spawn_point_1', token='G')
        self.battle.add(self.npc, 'b', position='spawn_point_2', token='g')
        self.npc.reset_turn(self.battle)
        self.fighter.reset_turn(self.battle)
        self.map.move_to(self.fighter, 1, 2, self.battle)
        self.map.move_to(self.npc, 1, 1, self.battle)

    def test_vallidate(self):
        action = GrappleAction.build(self.session, self.fighter)['next'](self.npc)
        action.validate(self.map)
        self.assertEqual(action.errors, [])


    def test_grappling(self):
        print(MapRenderer(self.map).render())
        action = GrappleAction.build(self.session, self.fighter)['next'](self.npc)
        random.seed(1000)
        self.battle.action(action)
        self.battle.commit(action)
        self.assertTrue(self.npc.grappled())

    def test_escape_grappling(self):
        self.npc.do_grappled_by(self.fighter)
        action = EscapeGrappleAction.build(self.session, self.npc)['next'](self.fighter)
        random.seed(1000)
        self.battle.action(action)
        self.battle.commit(action)
        self.assertFalse(self.npc.grappled())

    def test_movement_and_grappling(self):
        self.npc.do_grappled_by(self.fighter)
        print(MapRenderer(self.map).render())
        action = MoveAction(self.session, self.fighter, 'move',  { 'move_path' : [[1, 2], [1, 3]] })
        self.battle.action(action)
        self.battle.commit(action)
        print(MapRenderer(self.map).render())
        self.assertEqual(self.map.entity_or_object_pos(self.npc), [1, 2])

    def test_incapacitated_grappled_released(self):
        self.fighter.unconscious()
        self.assertFalse(self.npc.grappled())
