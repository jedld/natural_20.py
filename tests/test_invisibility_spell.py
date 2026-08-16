import random
import unittest

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.spell_loader import load_spell_class, spell_is_implemented


class InvisibilitySpellTestCase(unittest.TestCase):
    def setUp(self):
        random.seed(4411)
        event_manager = EventManager()
        event_manager.standard_cli()
        self.session = Session(root_path='tests/fixtures', event_manager=event_manager)
        self.battle_map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.battle_map)
        self.caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.ally = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.enemy = self.session.npc('goblin', {'name': 'Goblin'})
        self.battle_map.add(self.caster, 2, 2)
        self.battle_map.add(self.ally, 3, 2)
        self.battle_map.add(self.enemy, 2, 3)
        self.battle.add(self.caster, 'a', add_to_initiative=True)
        self.battle.add(self.ally, 'a', add_to_initiative=True)
        self.battle.add(self.enemy, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.caster, self.ally, self.enemy])
        self.caster.reset_turn(self.battle)

    def _cast(self, slug, target):
        action = SpellAction.build(self.session, self.caster)['next']([slug, 1])['next'](target)
        action.skip_consume_at_resolve = True
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.battle.commit(action)
        return action

    def test_yaml_and_loader(self):
        invis = self.session.load_spell('invisibility')
        greater = self.session.load_spell('greater_invisibility')
        self.assertEqual(invis['level'], 2)
        self.assertTrue(invis.get('concentration'))
        self.assertTrue(spell_is_implemented('invisibility', invis))
        self.assertEqual(greater['level'], 4)
        self.assertTrue(spell_is_implemented('greater_invisibility', greater))
        self.assertIsNotNone(load_spell_class('InvisibilitySpell'))
        self.assertIsNotNone(load_spell_class('GreaterInvisibilitySpell'))

    def test_invisibility_hides_from_sight_and_breaks_on_attack(self):
        self._cast('invisibility', self.ally)
        self.assertTrue(self.ally.invisible())
        self.assertTrue(self.battle_map.can_see(self.ally, self.enemy))
        self.assertFalse(self.battle_map.can_see(self.enemy, self.ally))

        self.ally.resolve_trigger('attack_resolved', {'target': self.enemy})
        self.assertFalse(self.ally.invisible())
        self.assertTrue(self.battle_map.can_see(self.enemy, self.ally))

    def test_invisibility_breaks_on_spell_cast(self):
        self._cast('invisibility', self.caster)
        self.assertTrue(self.caster.invisible())
        self.caster.resolve_trigger('spell_cast', {'spell': None})
        self.assertFalse(self.caster.invisible())

    def test_greater_invisibility_does_not_break_on_attack_or_cast(self):
        self._cast('greater_invisibility', self.caster)
        self.assertTrue(self.caster.invisible())
        self.assertFalse(self.battle_map.can_see(self.enemy, self.caster))

        self.caster.resolve_trigger('attack_resolved', {'target': self.enemy})
        self.assertTrue(self.caster.invisible())
        self.caster.resolve_trigger('spell_cast', {'spell': None})
        self.assertTrue(self.caster.invisible())
        self.assertFalse(self.battle_map.can_see(self.enemy, self.caster))

    def test_blindsight_perceives_invisible_creature(self):
        self._cast('greater_invisibility', self.ally)
        self.enemy.properties['blindsight'] = 60
        self.assertTrue(self.battle_map.can_see(self.enemy, self.ally))


if __name__ == '__main__':
    unittest.main()
