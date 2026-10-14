"""Remove Curse: ends curse effects (Hex), the cursed status, and cursed-item attunement."""
import random
import unittest

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.curses import has_curse, is_curse_effect


class RemoveCurseTest(unittest.TestCase):
    def setUp(self):
        random.seed(11)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'maps/empty_map')
        self.battle = Battle(self.session, self.map)
        self.cleric = PlayerCharacter.load(self.session, 'dwarf_cleric.yml')
        self.ally = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.warlock = PlayerCharacter.load(self.session, 'tiefling_warlock.yml')
        self.map.add(self.cleric, 1, 1)
        self.map.add(self.ally, 1, 2)
        self.map.add(self.warlock, 4, 4)
        self.battle.add(self.cleric, 'a', add_to_initiative=True)
        self.battle.add(self.ally, 'a', add_to_initiative=True)
        self.battle.add(self.warlock, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.warlock, self.cleric, self.ally])
        self.cleric.spell_slots.setdefault('cleric', {})[3] = 2
        self.cleric.properties.setdefault('prepared_spells', []).append('remove_curse')

    def cast(self, caster, spell, target, level):
        caster.reset_turn(self.battle)
        step = SpellAction.build(self.session, caster)['next']([spell, level])
        while isinstance(step, dict):
            first = step['param'][0]
            step = step['next']('str' if first['type'] == 'select_choice' else target)
        step.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(step)
        return step

    def hex_ally(self):
        self.warlock.properties.setdefault('prepared_spells', []).append('hex')
        self.warlock.spell_slots.setdefault('warlock', {})[1] = 2
        self.cast(self.warlock, 'hex', self.ally, 1)
        self.assertTrue(self.ally.has_effect('ability_check_advantage_modifier'))

    def test_hex_is_flagged_as_curse(self):
        self.hex_ally()
        self.assertTrue(is_curse_effect(self.warlock.concentration))
        self.assertTrue(has_curse(self.ally))

    def test_ends_hex_and_casters_concentration(self):
        self.hex_ally()
        self.cast(self.cleric, 'remove_curse', self.ally, 3)
        self.assertFalse(self.ally.has_effect('ability_check_advantage_modifier'))
        self.assertIsNone(self.warlock.concentration)
        self.assertFalse(has_curse(self.ally))
        self.assertEqual(self.cleric.spell_slots['cleric'][3], 1)

    def test_clears_cursed_status(self):
        self.ally.statuses.append('cursed')
        self.cast(self.cleric, 'remove_curse', self.ally, 3)
        self.assertNotIn('cursed', self.ally.statuses)

    def test_breaks_attunement_to_cursed_items(self):
        original = self.session.load_thing

        def load_thing(name):
            item = original(name)
            if name == 'longsword' and isinstance(item, dict):
                item = dict(item, cursed=True)
            return item

        self.session.load_thing = load_thing
        self.ally.properties['equipped'] = list(self.ally.properties.get('equipped', [])) + ['longsword']
        self.assertTrue(has_curse(self.ally))
        self.cast(self.cleric, 'remove_curse', self.ally, 3)
        self.assertIn('longsword', self.ally.properties['curse_broken_items'])
        self.assertFalse(has_curse(self.ally))

    def test_non_curse_effects_are_left_alone(self):
        self.cleric.properties['prepared_spells'].append('bless')
        self.cleric.spell_slots['cleric'][1] = 2
        self.cast(self.cleric, 'bless', [self.ally], 1)
        self.assertTrue(self.ally.has_effect('bless'))
        self.cast(self.cleric, 'remove_curse', self.ally, 3)
        self.assertTrue(self.ally.has_effect('bless'))
