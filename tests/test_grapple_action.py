import unittest
from natural20.actions.grapple_action import GrappleAction, DropGrappleAction
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

    def test_dragged_target_never_ends_on_occupied_square(self):
        # Issue #6 follow-up: the grappler may pass THROUGH an ally's
        # square, but the dragged target trails behind and must not END
        # there (SRD: you can never finish a move in another creature's
        # space). The target stops at the last free square of the trail.
        self.map.move_to(self.fighter, 1, 1, self.battle)
        self.map.move_to(self.npc, 0, 1, self.battle)
        ally = self.session.npc('goblin')
        self.battle.add(ally, 'a', position=[1, 2], token='h')
        self.npc.do_grappled_by(self.fighter)
        action = MoveAction(self.session, self.fighter, 'move',
                            {'move_path': [[1, 1], [1, 2], [1, 3]]})
        self.battle.action(action)
        self.battle.commit(action)
        # The ally blocks the normal trail square (1,2): the goblin stops
        # at (1,1), the fighter's start square (the grappler vacates it).
        self.assertEqual(self.map.entity_or_object_pos(self.fighter), [1, 3])
        self.assertEqual(self.map.entity_or_object_pos(ally), [1, 2])
        self.assertEqual(self.map.entity_or_object_pos(self.npc), [1, 1])

    def test_incapacitated_grappled_released(self):
        self.fighter.unconscious()
        self.assertFalse(self.npc.grappled())

    def test_drop_grapple(self):
        self.npc.do_grappled_by(self.fighter)
        self.assertTrue(self.fighter.is_grappling())
        action = DropGrappleAction.build(self.session, self.fighter)
        action.resolve(self.session, self.map)
        DropGrappleAction.apply(self.battle, action.result[0], session=self.session)
        self.assertFalse(self.fighter.is_grappling())
        self.assertFalse(self.npc.grappled())

    def test_resolve_incapacitated_target_auto_success(self):
        self.npc.update_state('unconscious')
        action = GrappleAction.build(self.session, self.fighter)['next'](self.npc)
        self.battle.action(action)
        item = action.result[0]
        self.assertTrue(item['success'])
        self.assertIsNone(item['target_roll'])

    def test_resolve_same_side_target_auto_success(self):
        ally = self.session.npc('goblin')
        self.battle.add(ally, 'a', position='spawn_point_3', token='g2')
        action = GrappleAction.build(self.session, self.fighter)['next'](ally)
        self.battle.action(action)
        item = action.result[0]
        self.assertTrue(item['success'])
        self.assertIsNone(item['target_roll'])
