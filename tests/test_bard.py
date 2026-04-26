import os
import random
import unittest
import numpy as np

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.battle import Battle
from natural20.map import Map
from natural20.actions.bardic_inspiration_action import BardicInspirationAction


class TestBard(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        np.random.seed(7000)
        random.seed(7000)
        self.bard = PlayerCharacter.load(self.session, 'human_bard.yml')
        self.battle.add(self.bard, 'a', position=[0, 5])
        self.battle.start()
        self.bard.reset_turn(self.battle)

    # ------------------------- core stats -------------------------

    def test_class_features_present(self):
        self.assertTrue(self.bard.class_feature('bardic_inspiration'))
        self.assertTrue(self.bard.class_feature('spellcasting'))
        self.assertTrue(self.bard.class_feature('jack_of_all_trades'))
        self.assertTrue(self.bard.class_feature('song_of_rest'))

    def test_spell_attack_modifier_uses_charisma(self):
        # CHA 16 -> +3, prof L2 -> +2 = +5
        self.assertEqual(self.bard.spell_attack_modifier(class_type='bard'), 5)

    def test_spell_save_dc(self):
        # 8 + prof + cha mod = 8 + 2 + 3 = 13
        self.assertEqual(self.bard.spell_save_dc(ability_type='charisma'), 13)

    def test_spell_slots_initialized(self):
        # Bard L2 -> 3 first-level slots
        self.assertEqual(self.bard.max_spell_slots(1, 'bard'), 3)
        self.assertEqual(self.bard.spell_slots_count(1, 'bard'), 3)

    # ------------------------- bardic inspiration -------------------------

    def test_bardic_inspiration_pool_initialized(self):
        # CHA mod 3 -> 3 uses
        self.assertEqual(self.bard.bardic_inspiration_max, 3)
        self.assertEqual(self.bard.bardic_inspiration_count, 3)
        self.assertTrue(self.bard.has_bardic_inspiration(1))

    def test_bardic_inspiration_die_at_low_levels(self):
        self.assertEqual(self.bard.bardic_inspiration_die(), '1d6')

    def test_bardic_inspiration_can_when_uses_remaining(self):
        self.assertTrue(BardicInspirationAction.can(self.bard, self.battle))
        self.bard.bardic_inspiration_count = 0
        self.assertFalse(BardicInspirationAction.can(self.bard, self.battle))

    def test_bardic_inspiration_consumes_use_and_bonus_action(self):
        ally = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(ally, 'a', position=[1, 5])
        ally.reset_turn(self.battle)

        action = BardicInspirationAction(self.session, self.bard, 'bardic_inspiration')
        action.target = ally
        action.resolve(self.session, None, {'battle': self.battle})
        self.battle.commit(action)

        self.assertEqual(self.bard.bardic_inspiration_count, 2)
        self.assertEqual(self.battle.entity_state_for(self.bard)['bonus_action'], 0)
        # Recipient is stamped with the bardic inspiration effect
        effects = [e for e in ally.casted_effects if e.get('effect') == 'bardic_inspiration']
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0]['die'], '1d6')

    def test_long_rest_refills_bardic_inspiration_and_slots(self):
        self.bard.consume_bardic_inspiration(2)
        self.bard.consume_spell_slot(1, 'bard')
        self.assertEqual(self.bard.bardic_inspiration_count, 1)
        self.assertEqual(self.bard.spell_slots_count(1, 'bard'), 2)

        # Long rest does not need an ended battle.
        self.bard.long_rest()
        self.assertEqual(self.bard.bardic_inspiration_count, 3)
        self.assertEqual(self.bard.spell_slots_count(1, 'bard'), 3)

    # ------------------------- jack of all trades -------------------------

    def test_jack_of_all_trades_bonus(self):
        # L2 prof bonus = 2 -> half = 1
        self.assertEqual(self.bard.jack_of_all_trades_bonus(), 1)

    def test_skill_check_mod_includes_jack_of_all_trades(self):
        # arcana is non-proficient (skills picked: performance, persuasion,
        # deception).  INT mod 1 + half prof 1 = 2.
        self.assertEqual(self.bard.arcana_mod(), 2)

    def test_skill_check_mod_proficient_unaffected_by_jack(self):
        # persuasion is proficient: CHA 3 + prof 2 = 5 (not 5 + half-prof)
        self.assertEqual(self.bard.persuasion_mod(), 5)


if __name__ == '__main__':
    unittest.main()
