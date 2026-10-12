import random
import unittest

from natural20.actions.grapple_action import DropGrappleAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.generic_controller import GenericController
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.ruleset import get_ruleset
from natural20.session import Session
from natural20.utils.grappling import (
    drag_cost_multiplier,
    drag_penalty,
    grapple_status_text,
)
from natural20.utils.jev_decision import _leaf_desc
from natural20.utils.movement import compute_actual_moves
from natural20.weapons import compute_advantages_and_disadvantages


class TestGrapplerRules(unittest.TestCase):
    def setUp(self):
        random.seed(7000)
        self.events = []
        self.event_manager = EventManager()
        self.event_manager.register_event_listener(
            ['drop_grapple'], lambda event: self.events.append(event))
        self.session = Session(root_path='tests/fixtures', event_manager=self.event_manager)
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        self.controller = GenericController(self.session)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.goblin = self.session.npc('goblin')
        self.battle.add(self.fighter, 'a', position='spawn_point_1', token='G')
        self.battle.add(self.goblin, 'b', position='spawn_point_2', token='g',
                        controller=self.controller)
        self.goblin.reset_turn(self.battle)
        self.fighter.reset_turn(self.battle)
        self.map.move_to(self.fighter, 1, 2, self.battle)
        self.map.move_to(self.goblin, 1, 1, self.battle)

    def test_grappler_released_when_held_creature_dies(self):
        self.fighter.do_grappled_by(self.goblin)
        self.fighter.attributes['grapple_escape_dcs'] = {self.goblin.entity_uid: 12}
        self.fighter.make_dead(self.battle)
        self.assertFalse(self.goblin.is_grappling())
        self.assertNotIn('grapple_escape_dcs', self.fighter.attributes)
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0]['reason'], 'target died')

    def test_drag_penalty_respects_size_exception(self):
        self.goblin.do_grappled_by(self.fighter)
        self.assertTrue(drag_penalty(self.fighter, phb_2024_rules=False))
        self.goblin.properties['size'] = 'tiny'
        self.assertFalse(drag_penalty(self.fighter, phb_2024_rules=False))
        self.assertEqual(drag_cost_multiplier(self.fighter), 1)

    def test_drag_halves_movement(self):
        path = [[1, 2], [1, 3]]
        free = compute_actual_moves(self.fighter, path, self.map, self.battle, 6)
        self.goblin.do_grappled_by(self.fighter)
        dragging = compute_actual_moves(self.fighter, path, self.map, self.battle, 6)
        self.assertEqual(free.budget - dragging.budget, 1)

    def test_grappler_attacks_other_targets_normally(self):
        other = self.session.npc('goblin')
        self.battle.add(other, 'b', position=[2, 2], token='h')
        self.goblin.do_grappled_by(self.fighter)
        _, disadvantage = compute_advantages_and_disadvantages(
            self.session, self.fighter, other, 'longsword', battle=self.battle)
        self.assertNotIn('grappling', disadvantage)

    def test_grappled_creature_attack_penalty_is_2024_only(self):
        self.fighter.do_grappled_by(self.goblin)
        other = self.session.npc('goblin')
        self.battle.add(other, 'b', position=[2, 2], token='h')
        _, disadvantage = compute_advantages_and_disadvantages(
            self.session, self.fighter, other, 'longsword', battle=self.battle)
        self.assertNotIn('grappled', disadvantage)
        self.session.ruleset = get_ruleset('5e-2024')
        _, disadvantage = compute_advantages_and_disadvantages(
            self.session, self.fighter, other, 'longsword', battle=self.battle)
        self.assertIn('grappled', disadvantage)
        _, disadvantage = compute_advantages_and_disadvantages(
            self.session, self.fighter, self.goblin, 'longsword', battle=self.battle)
        self.assertNotIn('grappled', disadvantage)

    def test_ai_releases_unconscious_target(self):
        self.fighter.do_grappled_by(self.goblin)
        self.fighter.attributes['hp'] = 0
        self.fighter.make_unconscious()
        action = self.controller.move_for(self.goblin, self.battle)
        self.assertIsInstance(action, DropGrappleAction)
        self.battle.action(action)
        self.battle.commit(action)
        self.assertFalse(self.goblin.is_grappling())
        self.assertFalse(self.fighter.grappled())
        self.assertEqual(len(self.events), 1)

    def test_ai_keeps_conscious_enemy_grappled(self):
        self.fighter.do_grappled_by(self.goblin)
        action = self.controller.move_for(self.goblin, self.battle)
        self.assertNotIsInstance(action, DropGrappleAction)

    def test_npc_offers_drop_grapple_option(self):
        self.fighter.do_grappled_by(self.goblin)
        self.battle.start()
        while self.battle.current_turn() is not self.goblin:
            self.battle.next_turn()
        actions = self.goblin.available_actions(self.session, self.battle)
        drops = [a for a in actions if isinstance(a, DropGrappleAction)]
        self.assertEqual([a.target for a in drops], [self.fighter])
        self.assertIn('release grapple on', _leaf_desc(drops[0]))

    def test_incapacitated_grappler_releases_at_turn_start(self):
        self.goblin.do_grappled_by(self.fighter)
        self.fighter.statuses.append('paralyzed')
        self.battle.start()
        while self.battle.current_turn() is not self.goblin:
            self.battle.next_turn()
        self.battle.start_turn()
        self.assertFalse(self.goblin.grappled())

    def test_out_of_reach_grapple_ends(self):
        self.goblin.do_grappled_by(self.fighter)
        self.map.move_to(self.goblin, 5, 5, self.battle)
        self.battle.start()
        while self.battle.current_turn() is not self.fighter:
            self.battle.next_turn()
        self.battle.start_turn()
        self.assertFalse(self.fighter.is_grappling())

    def test_status_text_tells_ai_about_halved_speed(self):
        self.goblin.do_grappled_by(self.fighter)
        txt = grapple_status_text(self.fighter)
        self.assertIn('grappling', txt)
        self.assertIn('speed halved', txt)
        self.assertIn('grappled by', grapple_status_text(self.goblin))


if __name__ == '__main__':
    unittest.main()
