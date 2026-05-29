import unittest

from natural20.actions.lay_on_hands_action import LayOnHandsAction
from natural20.battle import Battle
from natural20.utils.action_builder import autobuild
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


class TestLayOnHandsAction(unittest.TestCase):
    def setUp(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        self.session = Session(root_path='tests/fixtures', event_manager=event_manager)
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.paladin = PlayerCharacter.load(self.session, 'goliath_paladin.yml')
        self.ally = PlayerCharacter.load(self.session, 'halfling_rogue.yml')
        self.battle.add(self.paladin, 'a', position='spawn_point_1', token='P')
        self.battle.add(self.ally, 'a', position='spawn_point_2', token='A')
        self.map.move_to(self.paladin, 1, 2, self.battle)
        self.map.move_to(self.ally, 1, 1, self.battle)
        self.paladin.reset_turn(self.battle)
        self.ally.reset_turn(self.battle)

    def test_heal_specified_amount(self):
        starting_hp = self.ally.hp()
        self.ally.take_damage(7, battle=self.battle)
        missing_hp = starting_hp - self.ally.hp()
        self.assertEqual(missing_hp, 7)

        build = LayOnHandsAction.build(self.session, self.paladin)
        choice_step = build['next'](self.ally)
        self.assertIsInstance(choice_step, dict)
        choices = choice_step['param'][0]['choices']
        heal_choice = next(choice for choice in choices if choice[1] == 'heal:4')
        action = choice_step['next'](heal_choice)
        action.resolve(self.session, self.map, {'battle': self.battle})
        self.assertFalse(action.errors)
        self.assertEqual(action.heal_amt, 4)

        initial_pool = self.paladin.lay_on_hands_count
        self.battle.commit(action)

        self.assertEqual(self.ally.hp(), starting_hp - 3)
        self.assertEqual(self.paladin.lay_on_hands_count, initial_pool - 4)
        self.assertEqual(action.result[0]['mode'], 'heal')
        self.assertEqual(action.result[0]['hp'], 4)

    def test_cure_poison_spends_five_pool(self):
        self.ally.statuses.append('poisoned')
        self.assertTrue('poisoned' in self.ally.statuses)

        build = LayOnHandsAction.build(self.session, self.paladin)
        choice_step = build['next'](self.ally)
        self.assertIsInstance(choice_step, dict)
        choices = choice_step['param'][0]['choices']
        cure_choice = next(choice for choice in choices if choice[1] == 'cure:poison')
        action = choice_step['next'](cure_choice)
        action.resolve(self.session, self.map, {'battle': self.battle})
        self.assertFalse(action.errors)
        self.assertEqual(action.result[0]['mode'], 'cure')
        self.assertEqual(action.result[0]['conditions'], ['poisoned'])

        initial_pool = self.paladin.lay_on_hands_count
        self.battle.commit(action)

        self.assertNotIn('poisoned', self.ally.statuses)
        if hasattr(self.ally, 'poisoned'):
            self.assertFalse(self.ally.poisoned())
        self.assertEqual(self.paladin.lay_on_hands_count, initial_pool - 5)
        self.assertIn('poisoned', action.result[0].get('conditions', []))

    def test_autobuild_heal_choices(self):
        self.ally.take_damage(3, battle=self.battle)
        actions = autobuild(self.session, LayOnHandsAction, self.paladin, self.battle)
        self.assertTrue(actions)
        for action in actions:
            self.assertEqual(action.mode, 'heal')
            self.assertGreater(action.heal_amt, 0)
            self.assertFalse(action.errors)


if __name__ == '__main__':
    unittest.main()
