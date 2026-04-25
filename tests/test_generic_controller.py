import random
import unittest
from types import SimpleNamespace

from natural20.actions.first_aid_action import FirstAidAction
from natural20.actions.move_action import MoveAction
from natural20.actions.second_wind_action import SecondWindAction
from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.generic_controller import GenericController
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


class TestGenericController(unittest.TestCase):
    def setUp(self):
        random.seed(7000)
        event_manager = EventManager()
        event_manager.standard_cli()
        self.session = Session(root_path='tests/fixtures', event_manager=event_manager)

    def test_prefers_second_wind_when_badly_hurt(self):
        battle_map = Map(self.session, 'battle_sim')
        battle = Battle(self.session, battle_map)
        controller = GenericController(self.session)
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')

        battle.add(fighter, 'a', position='spawn_point_1', token='F', controller=controller)
        battle.start(combat_order=[fighter])
        fighter.reset_turn(battle)
        fighter.take_damage(60, session=self.session)

        choice = controller.move_for(fighter, battle)

        self.assertIsInstance(choice, SecondWindAction)

    def test_prefers_healing_spell_when_badly_hurt(self):
        battle_map = Map(self.session, 'battle_sim_objects')
        battle = Battle(self.session, battle_map)
        controller = GenericController(self.session)
        cleric = PlayerCharacter.load(self.session, 'dwarf_cleric.yml')

        battle.add(cleric, 'a', position=[0, 5], token='C', controller=controller)
        battle.start(combat_order=[cleric])
        cleric.reset_turn(battle)
        cleric.take_damage(6, session=self.session)

        choice = controller.move_for(cleric, battle)

        self.assertIsInstance(choice, SpellAction)
        self.assertEqual(choice.spell_action.short_name(), 'cure_wounds')
        self.assertEqual(choice.target, cleric)

    def test_prefers_first_aid_for_adjacent_downed_ally(self):
        battle_map = Map(self.session, 'battle_sim_objects')
        battle = Battle(self.session, battle_map)
        controller = GenericController(self.session)
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        ally = PlayerCharacter.load(self.session, 'halfling_rogue.yml')

        battle.add(fighter, 'a', position='spawn_point_1', token='F', controller=controller)
        battle.add(ally, 'a', position='spawn_point_2', token='A')
        battle_map.move_to(fighter, 1, 2, battle)
        battle_map.move_to(ally, 1, 1, battle)
        fighter.deduct_item('healing_potion', 1)
        ally.make_unconscious()

        battle.start(combat_order=[fighter, ally])
        fighter.reset_turn(battle)

        actions = controller._compute_available_moves(fighter, battle)
        self.assertTrue(any(isinstance(action, FirstAidAction) for action in actions))
        choice = controller.select_action(battle, fighter, actions)

        self.assertIsInstance(choice, FirstAidAction)
        self.assertEqual(choice.target, ally)

    def test_avoids_recent_move_destination_repetition(self):
        battle_map = Map(self.session, 'battle_sim')
        battle = Battle(self.session, battle_map)
        controller = GenericController(self.session)
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')

        battle.add(fighter, 'a', position='spawn_point_1', token='F', controller=controller)
        battle_map.move_to(fighter, 0, 5, battle)

        repeated_move = MoveAction(self.session, fighter, 'move')
        repeated_move.move_path = [[0, 5], [1, 5]]

        fresh_move = MoveAction(self.session, fighter, 'move')
        fresh_move.move_path = [[0, 5], [0, 6]]

        battle_data = controller._battle_data(battle, fighter)
        battle_data['recent_destinations'] = [(1, 5)]

        ordered_actions = controller._sort_actions(fighter, battle, [repeated_move, fresh_move])

        self.assertIs(ordered_actions[0], fresh_move)

    def test_support_spell_scoring_ignores_coordinate_targets(self):
        battle_map = Map(self.session, 'battle_sim_objects')
        battle = Battle(self.session, battle_map)
        controller = GenericController(self.session)
        cleric = PlayerCharacter.load(self.session, 'dwarf_cleric.yml')
        ally = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')

        battle.add(cleric, 'a', position=[0, 5], token='C', controller=controller)
        battle.add(ally, 'a', position=[1, 5], token='A')
        battle.start(combat_order=[cleric, ally])
        cleric.reset_turn(battle)

        fake_spell = object.__new__(SpellAction)
        fake_spell.target = [ally, (4, 4)]
        fake_spell.casting_time = 'action'
        fake_spell.spell_action = SimpleNamespace(short_name=lambda: 'bless')
        fake_spell.avg_damage = lambda _battle: 0

        ordered_actions = controller._sort_actions(cleric, battle, [fake_spell])

        self.assertEqual(ordered_actions, [fake_spell])


if __name__ == '__main__':
    unittest.main()