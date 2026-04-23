"""Tests that mutable per-character resources round-trip via to_dict/from_dict."""
import unittest

from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.npc import Npc
from natural20.session import Session


def _make_session():
    return Session(root_path='tests/fixtures', event_manager=EventManager())


class TestPlayerCharacterResourceSerialization(unittest.TestCase):
    def setUp(self):
        self.session = _make_session()

    def _round_trip(self, pc):
        data = pc.to_dict()
        return PlayerCharacter.from_dict(data)

    def test_hit_die_round_trip(self):
        pc = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        die = next(iter(pc._current_hit_die))
        pc._current_hit_die[die] = 0
        restored = self._round_trip(pc)
        self.assertEqual(restored._current_hit_die, pc._current_hit_die)

    def test_spell_slots_round_trip(self):
        pc = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        pc.spell_slots['wizard'][1] = 0
        restored = self._round_trip(pc)
        self.assertEqual(restored.spell_slots['wizard'][1], 0)
        # Independent copy.
        restored.spell_slots['wizard'][1] = 5
        self.assertEqual(pc.spell_slots['wizard'][1], 0)

    def test_wizard_arcane_recovery_round_trip(self):
        pc = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        pc.arcane_recovery = 0
        restored = self._round_trip(pc)
        self.assertEqual(restored.arcane_recovery, 0)

    def test_fighter_second_wind_round_trip(self):
        pc = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        pc.second_wind_count = 0
        restored = self._round_trip(pc)
        self.assertEqual(restored.second_wind_count, 0)

    def test_paladin_lay_on_hands_round_trip(self):
        pc = PlayerCharacter.load(self.session, 'goliath_paladin.yml')
        pc.lay_on_hands_count = 1
        restored = self._round_trip(pc)
        self.assertEqual(restored.lay_on_hands_count, 1)
        self.assertEqual(restored.lay_on_hands_max_pool, pc.lay_on_hands_max_pool)


class TestNpcResourceSerialization(unittest.TestCase):
    def setUp(self):
        self.session = _make_session()

    def test_npc_hit_die_round_trip(self):
        # Pull any npc from the fixtures directory.
        npc = Npc(self.session, 'goblin', {'name': 'goblin1'})
        die = next(iter(npc._current_hit_die))
        npc._current_hit_die[die] = 0
        data = npc.to_dict()
        restored = Npc.from_dict(data)
        self.assertEqual(restored._current_hit_die, npc._current_hit_die)
        self.assertEqual(restored._max_hit_die, npc._max_hit_die)


if __name__ == '__main__':
    unittest.main()
