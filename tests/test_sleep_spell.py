import random
import unittest
from unittest.mock import patch

from natural20.actions.help_action import HelpAction
from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.sleep_spell import SleepSpell
from natural20.utils.spell_loader import load_spell_class


class SleepSpellTestCase(unittest.TestCase):
    def setUp(self):
        random.seed(7200)
        event_manager = EventManager()
        event_manager.standard_cli()
        self.session = Session(root_path='tests/fixtures', event_manager=event_manager)
        self.battle_map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.battle_map)
        self.caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.low_hp = self.session.npc('goblin', {'name': 'Low HP Goblin'})
        self.low_hp.attributes['hp'] = 4
        self.high_hp = self.session.npc('goblin', {'name': 'High HP Goblin'})
        self.high_hp.attributes['hp'] = 12
        self.skeleton = self.session.npc('skeleton', {'name': 'Skeleton'})
        self.skeleton.properties['race'] = ['undead']
        self.battle_map.add(self.caster, 2, 2)
        self.battle_map.add(self.low_hp, 4, 2)
        self.battle_map.add(self.high_hp, 4, 3)
        self.battle_map.add(self.skeleton, 3, 2)
        self.battle.add(self.caster, 'a', add_to_initiative=True)
        self.battle.add(self.low_hp, 'b', add_to_initiative=True)
        self.battle.add(self.high_hp, 'b', add_to_initiative=True)
        self.battle.add(self.skeleton, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.caster, self.low_hp, self.high_hp, self.skeleton])
        self.caster.reset_turn(self.battle)

    def _cast_sleep(self, *, at_level=1):
        action = SpellAction.build(self.session, self.caster)['next'](['sleep', 1])['next']([4, 2])
        action.at_level = at_level
        action.spellcasting_class = 'wizard'
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.battle.commit(action)
        return action

    def test_yaml_and_loader(self):
        props = self.session.load_spell('sleep')
        self.assertEqual(props['level'], 1)
        self.assertEqual(props['radius'], 20)
        self.assertEqual(props['duration_seconds'], 60)
        self.assertIsNotNone(load_spell_class('SleepSpell'))

    @patch.object(DieRoll, 'roll')
    def test_hp_pool_affects_lowest_hp_first_and_skips_undead(self, mock_roll):
        mock_roll.return_value = DieRoll([2, 2, 2, 2, 2], 0, 8)

        action = self._cast_sleep()
        sleep_events = [r for r in action.result if r.get('type') == 'sleep']
        affected = {r['target'] for r in sleep_events}
        self.assertIn(self.low_hp, affected)
        self.assertNotIn(self.skeleton, affected)
        self.assertNotIn(self.high_hp, affected)
        self.assertIn('sleep', self.low_hp.statuses)
        self.assertIn('unconscious', self.low_hp.statuses)
        self.assertTrue(self.low_hp.incapacitated())

    @patch.object(DieRoll, 'roll')
    def test_damage_wakes_sleeper(self, mock_roll):
        mock_roll.return_value = DieRoll([4] * 5, 0, 8)
        self._cast_sleep()
        self.assertIn('sleep', self.low_hp.statuses)

        self.low_hp.take_damage(1, battle=self.battle)
        self.assertNotIn('sleep', self.low_hp.statuses)
        self.assertFalse(self.low_hp.unconscious())

    @patch.object(DieRoll, 'roll')
    def test_help_action_wakes_sleeper(self, mock_roll):
        mock_roll.return_value = DieRoll([4] * 5, 0, 8)
        self._cast_sleep()
        self.assertIn('sleep', self.low_hp.statuses)

        helper = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.battle_map.add(helper, 3, 2)
        self.battle.add(helper, 'a', add_to_initiative=False)
        helper.reset_turn(self.battle)

        help_action = HelpAction(self.session, helper, 'help')
        help_action.target = self.low_hp
        HelpAction.apply(self.battle, {
            'type': 'help',
            'source': helper,
            'target': self.low_hp,
            'battle': self.battle,
        }, session=self.session)
        self.assertNotIn('sleep', self.low_hp.statuses)

    @patch.object(DieRoll, 'roll')
    def test_upcast_increases_pool_dice(self, mock_roll):
        mock_roll.return_value = DieRoll([2] * 9, 0, 8)
        spell_cls = load_spell_class('SleepSpell')
        spell = spell_cls(self.session, self.caster, 'sleep', self.session.load_spell('sleep'))
        spell._pool_roll(self.battle, at_level=3)
        self.assertEqual(mock_roll.call_args.kwargs.get('description'), 'dice_roll.spells.sleep')
        self.assertEqual(mock_roll.call_args.args[0], '9d8')


if __name__ == '__main__':
    unittest.main()
