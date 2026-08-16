import random
import unittest
from unittest.mock import patch

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.blight_spell import BlightSpell
from natural20.spell.extensions.save_check import SaveCheck
from natural20.utils.spell_loader import load_spell_class, spell_is_implemented


class _MockSaveRoll:
    def __init__(self, total):
        self._total = total

    def result(self):
        return self._total

    def __lt__(self, other):
        return self._total < other


class BlightSpellTestCase(unittest.TestCase):
    def setUp(self):
        random.seed(4410)
        event_manager = EventManager()
        event_manager.standard_cli()
        self.session = Session(root_path='tests/fixtures', event_manager=event_manager)
        self.battle_map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.battle_map)
        self.caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.target = self.session.npc('goblin', {'name': 'Goblin'})
        self.battle_map.add(self.caster, 2, 2)
        self.battle_map.add(self.target, 3, 2)
        self.battle.add(self.caster, 'a', add_to_initiative=True)
        self.battle.add(self.target, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.caster, self.target])
        self.caster.reset_turn(self.battle)

    def _spell_action(self, target=None, *, at_level=4):
        target = target or self.target
        action = SpellAction.build(self.session, self.caster)['next'](['blight', 1])['next'](target)
        action.at_level = at_level
        action.spellcasting_class = 'wizard'
        action.skip_consume_at_resolve = True
        return action

    def test_yaml_and_loader(self):
        props = self.session.load_spell('blight')
        self.assertEqual(props['level'], 4)
        self.assertEqual(props['damage_type'], 'necrotic')
        self.assertTrue(spell_is_implemented('blight', props))
        self.assertIsNotNone(load_spell_class('BlightSpell'))

    @patch.object(DieRoll, 'roll')
    @patch.object(SaveCheck, 'make')
    def test_failed_save_deals_full_necrotic_damage(self, mock_save, mock_roll):
        mock_roll.return_value = DieRoll([4] * 8, 0, 8)
        mock_save.return_value = unittest.mock.Mock(passed=False, roll=_MockSaveRoll(5))

        action = self._spell_action()
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        damage_events = [r for r in action.result if r.get('type') == 'spell_damage']
        self.assertEqual(len(damage_events), 1)
        self.assertEqual(damage_events[0]['damage_type'], 'necrotic')
        self.assertEqual(damage_events[0]['damage'].result(), 32)
        self.assertTrue(damage_events[0]['save_failed'])

    @patch.object(DieRoll, 'roll')
    @patch.object(SaveCheck, 'make')
    def test_successful_save_deals_half_damage(self, mock_save, mock_roll):
        mock_roll.return_value = DieRoll([4] * 8, 0, 8)
        mock_save.return_value = unittest.mock.Mock(passed=True, roll=_MockSaveRoll(18))

        action = self._spell_action()
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        damage_events = [r for r in action.result if r.get('type') == 'spell_damage']
        self.assertEqual(damage_events[0]['damage'].result(), 16)
        self.assertFalse(damage_events[0]['save_failed'])

    @patch.object(SaveCheck, 'make')
    def test_plant_failed_save_takes_maximum_damage(self, mock_save):
        mock_save.return_value = unittest.mock.Mock(passed=False, roll=_MockSaveRoll(4))
        plant = self.session.npc('goblin', {'name': 'Vine Blight'})
        plant.properties['race'] = ['plant']
        self.battle_map.add(plant, 4, 2)
        self.battle.add(plant, 'b', add_to_initiative=True)

        action = self._spell_action(plant)
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        damage_events = [r for r in action.result if r.get('type') == 'spell_damage']
        self.assertEqual(damage_events[0]['damage'].result(), 64)
        self.assertIn('plant_blight', mock_save.call_args.kwargs.get('opts', {}).get('disadvantage', []))

    def test_undead_are_unaffected(self):
        undead = self.session.npc('skeleton', {'name': 'Skeleton'})
        self.battle_map.add(undead, 4, 3)
        self.battle.add(undead, 'b', add_to_initiative=True)
        action = self._spell_action(undead)
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.assertEqual(action.result[0]['type'], 'spell_miss')
        self.assertEqual(action.result[0].get('message'), 'immune')

    def test_upcast_adds_damage_dice(self):
        spell = BlightSpell(self.session, self.caster, 'BlightSpell', self.session.load_spell('blight'))
        with patch.object(DieRoll, 'roll', return_value=DieRoll([4] * 9, 0, 8)) as mock_roll:
            action = type('A', (), {'at_level': 5})()
            spell._damage(self.battle, spell_action=action)
            self.assertEqual(mock_roll.call_args.args[0], '9d8')


if __name__ == '__main__':
    unittest.main()
