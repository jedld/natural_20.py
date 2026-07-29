import random
import unittest
from unittest.mock import patch

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.web_spell import WebSpell
from natural20.utils.spell_loader import load_spell_class, spell_is_implemented


class WebSpellTestCase(unittest.TestCase):
    def setUp(self):
        random.seed(7201)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.battle_map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.battle_map)
        self.caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.target = self.session.npc('goblin', {'name': 'Goblin'})
        self.battle_map.add(self.caster, 2, 2)
        self.battle_map.add(self.target, 3, 3)
        self.battle.add(self.caster, 'a', add_to_initiative=True)
        self.battle.add(self.target, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.caster, self.target])
        self.caster.reset_turn(self.battle)

    def test_yaml_and_loader(self):
        props = self.session.load_spell('web')
        self.assertEqual(props['level'], 2)
        self.assertTrue(spell_is_implemented('web', props))
        self.assertIsNotNone(load_spell_class('WebSpell'))

    def test_build_map_uses_square_targeting(self):
        spell_cls = load_spell_class('WebSpell')
        spell = spell_cls(self.session, self.caster, 'WebSpell', self.session.load_spell('web'))
        action = SpellAction.build(self.session, self.caster)['next'](['web', 1])
        build_map = spell.build_map(action)
        self.assertEqual(build_map['param'][0]['type'], 'select_square')
        self.assertEqual(build_map['param'][0]['size'], 20)

    def test_failed_save_restrains_target_in_area(self):
        action = SpellAction.build(self.session, self.caster)['next'](['web', 1])['next']([3, 3])
        original_save = self.target.save_throw

        def low_save(ability, battle=None, opts=None):
            roll = original_save(ability, battle, opts)
            roll.rolls = [1]
            return roll

        self.target.save_throw = low_save
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.battle.commit(action)
        self.assertIn('restrained', self.target.statuses)
        self.assertTrue(self.battle.active_zones)


if __name__ == '__main__':
    unittest.main()
