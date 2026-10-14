"""Magic item attunement (natural20/utils/attunement.py)."""
import random
import unittest
from unittest import mock

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.ruleset.factory import get_ruleset
from natural20.session import Session
from natural20.utils import attunement
from natural20.utils.attunement import AttunementError
from natural20.utils.curses import break_curses
from natural20.utils.serialization import Serialization
from natural20.weapons import damage_modifier


class AttunementTest(unittest.TestCase):
    def setUp(self):
        random.seed(3)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.fighter.properties.pop('attuned', None)

    def give(self, *items, equip=False):
        for item in items:
            self.fighter.add_item(item)
            if equip:
                self.fighter.equip(item)

    def short_rest(self):
        self.fighter.short_rest(None, force=True)

    # --- legacy / seeding -------------------------------------------------

    def test_untracked_sheet_treats_equipped_items_as_attuned(self):
        before = self.fighter.armor_class()
        self.give('ring_of_protection', equip=True)
        self.assertFalse(attunement.tracking_enabled(self.fighter))
        self.assertEqual(self.fighter.armor_class(), before + 1)
        self.assertEqual(attunement.attuned_items(self.fighter), ['ring_of_protection'])

    def test_first_change_seeds_tracking_from_equipped_items(self):
        self.give('ring_of_protection', equip=True)
        self.give('cloak_of_protection')
        attunement.request_attunement(self.fighter, 'cloak_of_protection')
        self.assertEqual(self.fighter.properties['attuned'], ['ring_of_protection'])

    # --- attuning over a rest --------------------------------------------

    def test_attunement_waits_for_a_short_rest(self):
        self.fighter.properties['attuned'] = []
        before = self.fighter.armor_class()
        self.give('ring_of_protection', equip=True)
        self.assertEqual(self.fighter.armor_class(), before)
        result = attunement.request_attunement(self.fighter, 'ring_of_protection')
        self.assertEqual(result['status'], 'pending')
        self.assertEqual(self.fighter.armor_class(), before)
        self.short_rest()
        self.assertEqual(self.fighter.properties['attuned'], ['ring_of_protection'])
        self.assertNotIn('attunement_pending', self.fighter.properties)
        self.assertEqual(self.fighter.armor_class(), before + 1)

    def test_short_rest_completes_one_change_long_rest_two(self):
        self.fighter.properties['attuned'] = []
        items = ('ring_of_protection', 'cloak_of_protection', 'amulet_of_health')
        self.give(*items)
        for item in items:
            attunement.request_attunement(self.fighter, item)
        self.short_rest()
        self.assertEqual(self.fighter.properties['attuned'], ['ring_of_protection'])
        self.fighter.long_rest(force=True)
        self.assertEqual(sorted(self.fighter.properties['attuned']), sorted(items))

    def test_limit_of_three_counts_pending(self):
        self.fighter.properties['attuned'] = []
        items = ('ring_of_protection', 'cloak_of_protection', 'amulet_of_health', 'headband_of_intellect')
        self.give(*items)
        for item in items[:3]:
            attunement.request_attunement(self.fighter, item)
        with self.assertRaises(AttunementError):
            attunement.request_attunement(self.fighter, items[3])
        with self.assertRaises(AttunementError):
            attunement.request_attunement(self.fighter, items[3], force=True)

    def test_ending_frees_a_slot_in_the_same_rest(self):
        self.fighter.properties['attuned'] = ['ring_of_protection', 'cloak_of_protection', 'amulet_of_health']
        self.give('ring_of_protection', 'cloak_of_protection', 'amulet_of_health', 'headband_of_intellect')
        attunement.request_end(self.fighter, 'amulet_of_health')
        attunement.request_attunement(self.fighter, 'headband_of_intellect')
        self.fighter.long_rest(force=True)
        self.assertEqual(sorted(self.fighter.properties['attuned']),
                         ['cloak_of_protection', 'headband_of_intellect', 'ring_of_protection'])

    def test_must_hold_the_item(self):
        self.fighter.properties['attuned'] = []
        with self.assertRaises(AttunementError):
            attunement.request_attunement(self.fighter, 'ring_of_protection')

    def test_item_without_attunement_is_rejected(self):
        self.give('wand_of_magic_missiles')
        with self.assertRaises(AttunementError):
            attunement.request_attunement(self.fighter, 'wand_of_magic_missiles')

    def test_cancel_pending(self):
        self.fighter.properties['attuned'] = []
        self.give('ring_of_protection')
        attunement.request_attunement(self.fighter, 'ring_of_protection')
        attunement.cancel_pending(self.fighter, 'ring_of_protection')
        self.short_rest()
        self.assertEqual(self.fighter.properties['attuned'], [])

    def test_item_given_away_before_the_rest_fails(self):
        self.fighter.properties['attuned'] = []
        self.give('ring_of_protection')
        attunement.request_attunement(self.fighter, 'ring_of_protection')
        self.fighter.deduct_item('ring_of_protection')
        self.short_rest()
        self.assertEqual(self.fighter.properties['attuned'], [])
        self.assertNotIn('attunement_pending', self.fighter.properties)

    # --- prerequisites, curses, DM force -----------------------------------

    def test_class_prerequisite(self):
        self.give('test_wizard_staff')
        with self.assertRaises(AttunementError) as ctx:
            attunement.request_attunement(self.fighter, 'test_wizard_staff')
        self.assertIn('wizard', str(ctx.exception))
        result = attunement.request_attunement(self.fighter, 'test_wizard_staff', force=True)
        self.assertEqual(result['status'], 'attuned')

    def test_class_feature_can_waive_prerequisites_and_raise_limit(self):
        specs = [('artificer', {'feature': 'magic_item_savant', 'max': 5, 'ignore_prerequisites': True})]
        with mock.patch.object(attunement, '_class_specs', return_value=specs):
            self.assertEqual(attunement.attunement_limit(self.fighter), 5)
            self.give('test_wizard_staff')
            self.assertIsNone(attunement.attune_issue(self.fighter, 'test_wizard_staff'))

    def test_sheet_limit_override(self):
        self.fighter.properties['attunement_limit'] = 1
        self.assertEqual(attunement.attunement_limit(self.fighter), 1)

    def test_cursed_item_cannot_be_ended_until_curse_is_broken(self):
        self.give('test_cursed_amulet', equip=True)
        self.fighter.properties['attuned'] = ['test_cursed_amulet']
        with self.assertRaises(AttunementError):
            attunement.request_end(self.fighter, 'test_cursed_amulet')
        break_curses(self.fighter, self.session)
        self.assertEqual(self.fighter.properties['attuned'], [])

    # --- endings -----------------------------------------------------------

    def test_death_ends_attunement(self):
        self.give('ring_of_protection', equip=True)
        self.fighter.properties['attuned'] = ['ring_of_protection']
        self.fighter.make_dead()
        self.assertEqual(self.fighter.properties['attuned'], [])

    def test_separation_for_a_day_ends_attunement(self):
        self.session.register_entity(self.fighter)
        self.give('ring_of_protection', 'cloak_of_protection')
        self.fighter.properties['attuned'] = ['ring_of_protection', 'cloak_of_protection']
        self.fighter.deduct_item('ring_of_protection')
        self.fighter.deduct_item('cloak_of_protection')
        self.session.increment_game_time(3600)
        self.fighter.add_item('cloak_of_protection')
        self.session.increment_game_time(3600)
        self.session.increment_game_time(24 * 3600)
        self.assertEqual(self.fighter.properties['attuned'], ['cloak_of_protection'])
        self.assertNotIn('attunement_separated', self.fighter.properties)

    # --- unattuned items lose their magic ----------------------------------

    def test_unattuned_weapon_uses_mundane_form(self):
        self.give('test_attuned_blade', equip=True)
        self.fighter.properties['attuned'] = []
        weapon = self.session.load_weapon('test_attuned_blade')
        unattuned_mod = self.fighter.attack_roll_mod(weapon)
        self.assertEqual(damage_modifier(self.fighter, weapon), damage_modifier(self.fighter, dict(weapon, damage='1d8', magic_bonus=0, requires_attunement=False)))
        self.fighter.properties['attuned'] = ['test_attuned_blade']
        self.assertEqual(self.fighter.attack_roll_mod(weapon), unattuned_mod + 2)
        self.assertIn('1d6', damage_modifier(self.fighter, weapon))

    def test_unattuned_item_grants_no_resistance(self):
        self.give('test_cursed_amulet', equip=True)
        self.fighter.properties['attuned'] = []
        self.assertNotIn('cold', self.fighter.equipped_item_resistances())
        self.fighter.properties['attuned'] = ['test_cursed_amulet']
        self.assertIn('cold', self.fighter.equipped_item_resistances())

    # --- campaign knobs and editions ----------------------------------------

    def test_both_editions_use_three_items(self):
        for edition in ('5e-2014', '5e-2024'):
            self.session.ruleset = get_ruleset(edition)
            self.assertEqual(attunement.attunement_limit(self.fighter), 3)
            self.assertTrue(attunement.requires_rest(self.fighter))

    def test_no_rest_house_rule_attunes_instantly(self):
        self.session.ruleset = get_ruleset('5e-2024', overrides={'attunement_requires_rest': False})
        self.fighter.properties['attuned'] = []
        self.give('ring_of_protection')
        result = attunement.request_attunement(self.fighter, 'ring_of_protection')
        self.assertEqual(result['status'], 'attuned')
        result = attunement.request_end(self.fighter, 'ring_of_protection')
        self.assertEqual(result['status'], 'ended')

    def test_status_model(self):
        self.fighter.properties['attuned'] = []
        self.give('ring_of_protection', equip=True)
        self.give('test_wizard_staff')
        attunement.request_attunement(self.fighter, 'ring_of_protection')
        status = attunement.attunement_status(self.fighter)
        self.assertEqual(status['limit'], 3)
        rows = {row['item']: row for row in status['items']}
        self.assertEqual(rows['ring_of_protection']['pending'], 'attune')
        self.assertIsNotNone(rows['test_wizard_staff']['issue'])
        card = self.fighter.item_card('ring_of_protection')
        self.assertEqual(card['attunement']['pending'], 'attune')

    def test_save_load_keeps_attunement_state(self):
        self.give('ring_of_protection', 'cloak_of_protection')
        self.fighter.properties['attuned'] = ['ring_of_protection']
        attunement.request_attunement(self.fighter, 'cloak_of_protection')
        battle_map = Map(self.session, 'maps/empty_map')
        battle_map.add(self.fighter, 0, 0)
        battle = Battle(self.session, battle_map)
        battle.add(self.fighter, 'a')
        dump = Serialization().serialize(self.session, battle, {'empty_map': battle_map})
        session2, _battle2, _maps2 = Serialization().deserialize(dump)
        fighter2 = session2.entity_by_uid(self.fighter.entity_uid)
        self.assertEqual(fighter2.properties['attuned'], ['ring_of_protection'])
        self.assertEqual(attunement.pending_changes(fighter2),
                         [{'item': 'cloak_of_protection', 'mode': 'attune'}])


if __name__ == '__main__':
    unittest.main()
