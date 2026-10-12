import random
import unittest

from natural20.actions.attack_action import AttackAction
from natural20.actions.move_action import MoveAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.generic_controller import GenericController
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.actions.dodge_action import DodgeAction
from natural20.utils.legendary_actions import (
    legendary_action_cost,
    legendary_pool_size,
    prepare_legendary_phase_action,
)
from natural20.web.web_controller import WebController


class TestLegendaryActions(unittest.TestCase):
    def setUp(self):
        random.seed(1234)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'tests/fixtures/jev_arena.yml')
        self.session.register_map('arena', self.map)
        self.battle = Battle(self.session, self.map)
        self.controller = GenericController(self.session)

    def _add_pc(self, pos):
        pc = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(pc, 'a', position=pos, add_to_initiative=True)
        pc.reset_turn(self.battle)
        return pc

    def _add_brute(self, pos):
        brute = self.session.npc('legendary_brute')
        self.map.add(brute, *pos)
        self.battle.add(brute, 'b', controller=self.controller, add_to_initiative=True)
        return brute

    def _end_turn_of(self, entity):
        self.battle.set_current_turn(entity)
        self.battle.end_turn()

    def test_pool_is_full_before_first_turn(self):
        self._add_pc([0, 0])
        brute = self._add_brute([5, 5])
        self.battle.start()
        self.assertEqual(legendary_pool_size(brute), 3)
        self.assertEqual(brute.total_legendary_actions(self.battle), 3)

    def test_pool_size_from_yaml(self):
        brute = self.session.npc('legendary_brute')
        brute.properties = dict(brute.properties, legendary_action_count=2)
        self.assertEqual(legendary_pool_size(brute), 2)

    def test_cost_helper(self):
        self.assertEqual(legendary_action_cost({'name': 'claw'}), 1)
        self.assertEqual(legendary_action_cost({'name': 'maul', 'cost': 2}), 2)
        self.assertEqual(legendary_action_cost(None), 1)

    def test_attacks_any_enemy_in_reach_not_just_turn_ender(self):
        far_pc = self._add_pc([0, 0])
        near_pc = self._add_pc([5, 4])
        brute = self._add_brute([5, 5])
        self.battle.start()

        candidates = self.controller.legendary_action_candidates(self.battle, self.session, brute)
        targets = {a.target for a in candidates if isinstance(a, AttackAction)}
        self.assertEqual(targets, {near_pc})

        self._end_turn_of(far_pc)

        # Prefers the 2-cost maul (higher damage per action spent).
        self.assertEqual(brute.total_legendary_actions(self.battle), 1)
        self.assertEqual(self.map.position_of(brute), [5, 5])

    def test_cost_gates_expensive_options(self):
        pc = self._add_pc([5, 4])
        brute = self._add_brute([5, 5])
        self.battle.start()
        self.battle.entity_state_for(brute)['legendary_actions'] = 1

        candidates = self.controller.legendary_action_candidates(self.battle, self.session, brute)
        names = {a.npc_action['name'] for a in candidates if isinstance(a, AttackAction)}
        self.assertEqual(names, {'claw'})

        other = self._add_pc([0, 0])
        self._end_turn_of(other)
        self.assertEqual(brute.total_legendary_actions(self.battle), 0)

    def test_legendary_move_closes_distance_without_spending_movement(self):
        pc = self._add_pc([0, 0])
        brute = self._add_brute([6, 4])
        self.battle.start()
        movement_before = self.battle.entity_state_for(brute)['movement']

        self._end_turn_of(pc)

        self.assertLessEqual(self.map.distance(brute, pc), 1)
        self.assertEqual(brute.total_legendary_actions(self.battle), 2)
        self.assertEqual(self.battle.entity_state_for(brute)['movement'], movement_before)

    def test_legendary_move_out_of_reach_does_nothing(self):
        pc = self._add_pc([0, 0])
        # 9 squares away: more than a 30 ft legendary move can cover.
        brute = self._add_brute([9, 7])
        self.battle.start()

        self._end_turn_of(pc)

        self.assertEqual(self.map.position_of(brute), [9, 7])
        self.assertEqual(brute.total_legendary_actions(self.battle), 3)

    def test_no_legendary_action_on_own_turn(self):
        self._add_pc([5, 4])
        brute = self._add_brute([5, 5])
        self.battle.start()
        self._end_turn_of(brute)
        self.assertEqual(brute.total_legendary_actions(self.battle), 3)

    def test_move_action_serializes_legendary_flags(self):
        brute = self._add_brute([5, 5])
        action = MoveAction(self.session, brute, 'move')
        action.move_path = [[5, 5], [4, 4]]
        action.legendary_action = True
        action.legendary_cost = 2
        action.ignore_opportunity_attacks = True
        data = action.to_dict()
        data['session'] = self.session
        data['source'] = brute
        restored = MoveAction.from_dict(data)
        self.assertTrue(restored.legendary_action)
        self.assertEqual(restored.legendary_cost, 2)
        self.assertTrue(restored.ignore_opportunity_attacks)


class TestManualLegendaryPhase(unittest.TestCase):
    """Manually controlled (web) legendary creatures get a phase window
    instead of the heuristic auto-pick."""

    def setUp(self):
        random.seed(1234)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'tests/fixtures/jev_arena.yml')
        self.session.register_map('arena', self.map)
        self.battle = Battle(self.session, self.map)

    def _add_pc(self, pos):
        pc = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(pc, 'a', position=pos, add_to_initiative=True)
        pc.reset_turn(self.battle)
        return pc

    def _add_manual_brute(self, pos):
        brute = self.session.npc('legendary_brute')
        self.map.add(brute, *pos)
        self.battle.add(brute, 'b', controller=WebController(self.session, 'dm'), add_to_initiative=True)
        return brute

    def _end_turn_of(self, entity):
        self.battle.set_current_turn(entity)
        self.battle.end_turn()

    def test_end_turn_queues_phase_instead_of_acting(self):
        pc = self._add_pc([5, 4])
        brute = self._add_manual_brute([5, 5])
        self.battle.start()

        self._end_turn_of(pc)

        self.assertEqual(brute.total_legendary_actions(self.battle), 3)
        self.assertEqual(self.battle.pending_legendary_phases, [brute.entity_uid])
        self.assertIsNone(self.battle.legendary_phase)

        self.assertIs(self.battle.begin_legendary_phase(), brute)
        self.assertTrue(self.battle.in_legendary_phase(brute))
        self.assertIs(self.battle.legendary_phase_entity(), brute)
        self.assertIsNone(self.battle.begin_legendary_phase())
        self.assertIsNone(self.battle.legendary_phase)

    def test_phase_offers_only_legendary_actions_and_full_speed_move(self):
        pc = self._add_pc([5, 4])
        brute = self._add_manual_brute([5, 5])
        self.battle.start()
        self.battle.entity_state_for(brute)['movement'] = 0
        self._end_turn_of(pc)
        self.battle.begin_legendary_phase()

        actions = brute.available_actions(self.session, self.battle, auto_target=False)
        attack_names = {a.npc_action['name'] for a in actions if isinstance(a, AttackAction)}
        moves = [a for a in actions if isinstance(a, MoveAction)]
        self.assertEqual(attack_names, {'claw', 'maul'})
        self.assertTrue(all(a.legendary_action for a in actions))
        self.assertEqual(len(moves), 1)
        self.assertTrue(moves[0].ignore_opportunity_attacks)
        self.assertEqual(brute.available_movement(self.battle), brute.speed())
        self.assertEqual(brute.available_actions(self.session, self.battle, interact_only=True), [])

    def test_prepare_marks_manual_actions_as_legendary(self):
        pc = self._add_pc([5, 4])
        brute = self._add_manual_brute([5, 5])
        self.battle.start()
        self._end_turn_of(pc)
        self.battle.begin_legendary_phase()

        attack = AttackAction(self.session, brute, 'attack')
        attack.npc_action = {'name': 'maul'}
        self.assertIsNone(prepare_legendary_phase_action(brute, self.battle, attack))
        self.assertTrue(attack.legendary_action)
        self.assertEqual(legendary_action_cost(attack.npc_action), 2)

        move = MoveAction(self.session, brute, 'move')
        self.assertIsNone(prepare_legendary_phase_action(brute, self.battle, move))
        self.assertTrue(move.legendary_action)

        not_legendary = AttackAction(self.session, brute, 'attack')
        not_legendary.npc_action = {'name': 'bite'}
        self.assertIsNotNone(prepare_legendary_phase_action(brute, self.battle, not_legendary))
        self.assertIsNotNone(prepare_legendary_phase_action(brute, self.battle, DodgeAction(self.session, brute, 'dodge')))

    def test_manual_legendary_attack_spends_pool(self):
        pc = self._add_pc([5, 4])
        brute = self._add_manual_brute([5, 5])
        self.battle.start()
        self._end_turn_of(pc)
        self.battle.begin_legendary_phase()

        attack = AttackAction(self.session, brute, 'attack')
        attack.npc_action = {'name': 'maul'}
        attack.target = pc
        prepare_legendary_phase_action(brute, self.battle, attack)
        self.battle.action(attack)
        self.battle.commit(attack)

        self.assertEqual(brute.total_legendary_actions(self.battle), 1)

    def test_phase_survives_serialization(self):
        pc = self._add_pc([5, 4])
        brute = self._add_manual_brute([5, 5])
        self.battle.start()
        self._end_turn_of(pc)
        self.battle.begin_legendary_phase()

        data = self.battle.to_dict()
        self.assertEqual(data['legendary_phase'], brute.entity_uid)
        restored = Battle.from_dict(data)
        self.assertEqual(restored.legendary_phase, brute.entity_uid)
        self.assertEqual(restored.pending_legendary_phases, [])


if __name__ == '__main__':
    unittest.main()
