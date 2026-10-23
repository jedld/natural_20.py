"""Beacon of Hope: WIS/death save advantage and maximized healing."""
import random
import unittest
from unittest import mock

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.beacon_of_hope_spell import BeaconOfHopeSpell
from natural20.utils.healing import effective_heal_roll
from natural20.utils.serialization import Serialization


class BeaconOfHopeTest(unittest.TestCase):
    def setUp(self):
        random.seed(99)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'maps/empty_map')
        self.battle = Battle(self.session, self.map)
        self.cleric = PlayerCharacter.load(self.session, 'dwarf_cleric.yml')
        self.ally = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.goblin = self.session.npc('goblin', {'name': 'Goblin'})
        self.map.add(self.cleric, 1, 1)
        self.map.add(self.ally, 0, 2)
        self.map.add(self.goblin, 3, 3)
        self.battle.add(self.cleric, 'a', add_to_initiative=True)
        self.battle.add(self.ally, 'a', add_to_initiative=True)
        self.battle.add(self.goblin, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.cleric, self.ally, self.goblin])
        self.cleric.reset_turn(self.battle)
        self.cleric.spell_slots.setdefault('cleric', {})[3] = 2
        self.cleric.properties.setdefault('prepared_spells', []).append('beacon_of_hope')

    def cast(self, targets):
        action = SpellAction.build(self.session, self.cleric)['next'](['beacon_of_hope', 3])['next'](targets)
        action.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(action)
        return action

    def test_buffs_every_chosen_creature_with_one_concentration(self):
        self.cast([self.cleric, self.ally])
        self.assertIsInstance(self.cleric.concentration, BeaconOfHopeSpell)
        for target in (self.cleric, self.ally):
            self.assertTrue(target.has_effect('max_healing'))
            self.assertTrue(target.has_effect('death_save_advantage_modifier'))
        self.assertFalse(self.goblin.has_effect('max_healing'))
        self.assertEqual(self.cleric.spell_slots['cleric'][3], 1)

    def test_wisdom_saves_have_advantage_but_not_others(self):
        self.cast([self.ally])
        adv, _ = self.ally.eval_effect('save_advantage_modifier', {'value': [[], []], 'save_type': 'wisdom'})
        self.assertIn('beacon_of_hope', adv)
        adv, _ = self.ally.eval_effect('save_advantage_modifier', {'value': [[], []], 'save_type': 'dexterity'})
        self.assertNotIn('beacon_of_hope', adv)

    def test_death_saves_roll_with_advantage(self):
        self.cast([self.ally])
        self.ally.take_damage(self.ally.hp(), battle=self.battle)
        self.assertTrue(self.ally.unconscious())
        captured = {}
        original = DieRoll.roll_with_lucky

        def spy(entity, roll_str, **kwargs):
            captured.update(kwargs)
            return original(entity, roll_str, **kwargs)

        with mock.patch.object(DieRoll, 'roll_with_lucky', side_effect=spy):
            self.ally.death_saving_throw(self.battle)
        self.assertTrue(captured.get('advantage'))
        self.assertFalse(captured.get('disadvantage'))

    def test_healing_is_maximized(self):
        self.cast([self.ally])
        roll = DieRoll.roll('2d8+3')
        self.assertEqual(effective_heal_roll(self.ally, roll).result(), 19)
        self.assertIs(effective_heal_roll(self.goblin, roll), roll)

        self.ally.take_damage(self.ally.hp() - 1, battle=self.battle)
        self.cleric.properties['prepared_spells'].append('cure_wounds')
        self.cleric.spell_slots['cleric'][1] = 2
        action = SpellAction.build(self.session, self.cleric)['next'](['cure_wounds', 1])['next'](self.ally)
        action.resolve(self.session, self.map, {'battle': self.battle})
        heal = next(i for i in action.result if i['type'] == 'spell_heal')
        before = self.ally.hp()
        self.battle.commit(action)
        self.assertTrue(heal['heal_roll'].metadata.get('maximized'))
        self.assertEqual(heal['heal_roll'].result(), heal['heal_roll'].max_result())
        self.assertGreaterEqual(self.ally.hp() - before,
                                min(self.ally.max_hp() - before, heal['heal_roll'].max_result()))

    def test_dropping_concentration_clears_all_targets(self):
        self.cast([self.cleric, self.ally])
        self.cleric.dismiss_effect(self.cleric.concentration)
        self.assertFalse(self.ally.has_effect('max_healing'))
        self.assertFalse(self.cleric.has_effect('max_healing'))

    def test_dismiss_with_tuple_target_from_auto_targeting(self):
        # The auto-targeting builder (natural20/utils/action_builder.py)
        # passes multi-target combinations as tuples, so a failed
        # concentration check (take_damage -> dismiss_effect) must clear
        # every target for tuple targets exactly like list targets.
        self.cast((self.cleric, self.ally))
        self.assertTrue(self.ally.has_effect('max_healing'))
        self.cleric.dismiss_effect(self.cleric.concentration)
        self.assertFalse(self.ally.has_effect('max_healing'))
        self.assertFalse(self.cleric.has_effect('max_healing'))

    def test_save_load_round_trip(self):
        self.cast([self.cleric, self.ally])
        dump = Serialization().serialize(self.session, self.battle, {'empty_map': self.map})
        session2, _battle2, _maps2 = Serialization().deserialize(dump)
        ally2 = session2.entity_by_uid(self.ally.entity_uid)
        cleric2 = session2.entity_by_uid(self.cleric.entity_uid)
        self.assertTrue(ally2.has_effect('max_healing'))
        cleric2.dismiss_effect(cleric2.concentration)
        self.assertFalse(ally2.has_effect('max_healing'))


class DieRollMaximizedTest(unittest.TestCase):
    def test_maximized_and_max_result(self):
        roll = DieRoll.roll('3d6+2')
        self.assertEqual(roll.max_result(), 20)
        self.assertEqual(roll.maximized().result(), 20)
