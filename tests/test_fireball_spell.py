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
from natural20.spell.extensions.save_check import SaveCheck
from natural20.spell.wizard_spells import FireballSpell
from natural20.utils.spell_loader import load_spell_class


class _MockSaveRoll:
    def __init__(self, total):
        self._total = total

    def result(self):
        return self._total

    def __lt__(self, other):
        return self._total < other


class FireballSpellTestCase(unittest.TestCase):
    def setUp(self):
        random.seed(7100)
        event_manager = EventManager()
        event_manager.standard_cli()
        self.session = Session(root_path='tests/fixtures', event_manager=event_manager)
        self.battle_map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.battle_map)
        self.caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.caster.properties['classes'] = {'wizard': 5}
        self.caster.properties['level'] = 5
        self.goblin = self.session.npc('goblin', {'name': 'Goblin A'})
        self.battle_map.add(self.caster, 2, 2)
        self.battle_map.add(self.goblin, 4, 2)
        self.battle.add(self.caster, 'a', add_to_initiative=True)
        self.battle.add(self.goblin, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.caster, self.goblin])
        self.caster.reset_turn(self.battle)

    def _spell_action(self, *, at_level=3):
        props = self.session.load_spell('fireball')
        action = SpellAction.build(self.session, self.caster)['next'](['fireball', 1])['next']([4, 2])
        action.at_level = at_level
        action.spellcasting_class = 'wizard'
        return action

    def test_yaml_and_loader(self):
        props = self.session.load_spell('fireball')
        self.assertEqual(props['level'], 3)
        self.assertEqual(props['radius'], 20)
        self.assertEqual(props['damage_type'], 'fire')
        self.assertIsNotNone(load_spell_class('FireballSpell'))

    def test_build_map_uses_radius_targeting(self):
        spell_cls = load_spell_class('FireballSpell')
        spell = spell_cls(self.session, self.caster, 'fireball', self.session.load_spell('fireball'))
        action = SpellAction.build(self.session, self.caster)['next'](['fireball', 1])
        build_map = spell.build_map(action)
        self.assertEqual(build_map['param'][0]['type'], 'select_radius')
        self.assertEqual(build_map['param'][0]['radius'], 20)
        self.assertFalse(build_map['param'][0]['require_los'])

    def test_validate_allows_point_without_line_of_sight(self):
        spell_cls = load_spell_class('FireballSpell')
        props = self.session.load_spell('fireball')
        spell = spell_cls(self.session, self.caster, 'FireballSpell', props)
        spell.validate(self.battle_map, target=[4, 2])
        self.assertEqual(spell.errors, [])

    def test_validate_rejects_out_of_range_point(self):
        spell_cls = load_spell_class('FireballSpell')
        props = self.session.load_spell('fireball')
        spell = spell_cls(self.session, self.caster, 'FireballSpell', props)
        spell.validate(self.battle_map, target=[40, 40])
        self.assertTrue(spell.errors)

    @patch.object(DieRoll, 'roll')
    @patch.object(SaveCheck, 'make')
    def test_failed_save_deals_full_fire_damage(self, mock_save, mock_roll):
        mock_roll.return_value = DieRoll([4] * 8, 0, 6)
        mock_save.return_value = unittest.mock.Mock(passed=False, roll=_MockSaveRoll(8))

        action = self._spell_action()
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        damage_events = [r for r in action.result if r.get('type') == 'spell_damage']
        self.assertGreaterEqual(len(damage_events), 1)
        self.assertEqual(damage_events[0]['damage_type'], 'fire')
        self.assertEqual(damage_events[0]['damage'].result(), 32)
        self.assertTrue(damage_events[0]['save_failed'])

    @patch.object(DieRoll, 'roll')
    @patch.object(SaveCheck, 'make')
    def test_successful_save_deals_half_damage(self, mock_save, mock_roll):
        mock_roll.return_value = DieRoll([4, 4, 4, 4, 3, 3, 4, 4], 0, 6)
        mock_save.return_value = unittest.mock.Mock(passed=True, roll=_MockSaveRoll(18))

        action = self._spell_action()
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        damage_events = [r for r in action.result if r.get('type') == 'spell_damage']
        self.assertEqual(damage_events[0]['damage'].result(), 15)
        self.assertFalse(damage_events[0]['save_failed'])

    @patch.object(DieRoll, 'roll')
    def test_upcast_adds_damage_dice(self, mock_roll):
        mock_roll.return_value = DieRoll([5] * 9, 0, 6)
        spell_cls = load_spell_class('FireballSpell')
        spell = spell_cls(self.session, self.caster, 'fireball', self.session.load_spell('fireball'))
        spell._damage(self.battle, opts={'at_level': 4})
        self.assertEqual(mock_roll.call_args.args[0], '9d6')


if __name__ == '__main__':
    unittest.main()
