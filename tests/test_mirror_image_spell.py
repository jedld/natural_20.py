import random
import unittest

from natural20.actions.attack_action import AttackAction
from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.mirror_image_spell import MirrorImageSpell
from natural20.utils.spell_loader import load_spell_class, spell_is_implemented


class MirrorImageSpellTestCase(unittest.TestCase):
    def setUp(self):
        random.seed(7202)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.battle_map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.battle_map)
        self.caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.attacker = self.session.npc('goblin', {'name': 'Goblin'})
        self.battle_map.add(self.caster, 2, 2)
        self.battle_map.add(self.attacker, 3, 2)
        self.battle.add(self.caster, 'a', add_to_initiative=True)
        self.battle.add(self.attacker, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.caster, self.attacker])
        self.caster.reset_turn(self.battle)

    def test_yaml_and_loader(self):
        props = self.session.load_spell('mirror_image')
        self.assertEqual(props['level'], 2)
        self.assertTrue(spell_is_implemented('mirror_image', props))
        self.assertIsNotNone(load_spell_class('MirrorImageSpell'))

    def test_cast_applies_mirror_image_status(self):
        action = SpellAction.build(self.session, self.caster)['next'](['mirror_image', 1])['next'](self.caster)
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.battle.commit(action)
        self.assertIn('mirror_image', self.caster.statuses)

    def test_high_roll_hits_duplicate_not_caster(self):
        action = SpellAction.build(self.session, self.caster)['next'](['mirror_image', 1])['next'](self.caster)
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.battle.commit(action)

        attack_roll = DieRoll.roll('1d20+5', battle=self.battle, entity=self.attacker)
        attack_roll.rolls = [15]
        redirected = MirrorImageSpell.mirror_image_redirect(self.caster, attack_roll, self.battle)
        self.assertTrue(redirected)
        self.assertEqual(MirrorImageSpell._images_remaining(self.caster), 2)


if __name__ == '__main__':
    unittest.main()
