"""Tests for the per-PC journal feature."""
import unittest

from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.session import Session


def _make_session():
    return Session(root_path='tests/fixtures', event_manager=EventManager())


class TestPlayerCharacterJournal(unittest.TestCase):
    def setUp(self):
        self.session = _make_session()
        self.pc = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')

    def test_new_pc_has_empty_journal(self):
        self.assertEqual(self.pc.journal, [])

    def test_add_entry_returns_payload_and_appends(self):
        entry = self.pc.add_journal_entry("Investigated the foyer.", kind='note')
        self.assertIsNotNone(entry)
        self.assertEqual(entry['text'], "Investigated the foyer.")
        self.assertEqual(entry['kind'], 'note')
        self.assertIn('id', entry)
        self.assertIn('ts', entry)
        self.assertEqual(self.pc.journal[-1], entry)

    def test_blank_entries_are_ignored(self):
        self.assertIsNone(self.pc.add_journal_entry("   "))
        self.assertIsNone(self.pc.add_journal_entry(""))
        self.assertEqual(self.pc.journal, [])

    def test_consecutive_duplicate_narration_is_deduped(self):
        first = self.pc.add_journal_entry("A door slams shut.", kind='narration', source='basement')
        second = self.pc.add_journal_entry("A door slams shut.", kind='narration', source='basement')
        self.assertEqual(first, second)
        self.assertEqual(len(self.pc.journal), 1)
        # A different source should be allowed through.
        self.pc.add_journal_entry("A door slams shut.", kind='narration', source='attic')
        self.assertEqual(len(self.pc.journal), 2)
        # Manual notes are never deduped.
        self.pc.add_journal_entry("A door slams shut.", kind='note')
        self.pc.add_journal_entry("A door slams shut.", kind='note')
        self.assertEqual(len(self.pc.journal), 4)

    def test_search_returns_substring_matches(self):
        self.pc.add_journal_entry("Found the silver key in the dining room.")
        self.pc.add_journal_entry("Strahd appeared and warned us.", title='Encounter')
        self.pc.add_journal_entry("Bought rations in town.", tags=['shopping'])
        self.assertEqual(len(self.pc.search_journal()), 3)
        self.assertEqual(len(self.pc.search_journal('silver')), 1)
        self.assertEqual(len(self.pc.search_journal('encounter')), 1)
        self.assertEqual(len(self.pc.search_journal('SHOPPING')), 1)
        self.assertEqual(len(self.pc.search_journal('nope')), 0)

    def test_search_filters_by_kind_and_limit(self):
        for i in range(3):
            self.pc.add_journal_entry(f"narrated {i}", kind='narration')
        for i in range(2):
            self.pc.add_journal_entry(f"noted {i}", kind='note')
        self.assertEqual(len(self.pc.search_journal(kind='narration')), 3)
        self.assertEqual(len(self.pc.search_journal(kind='note')), 2)
        self.assertEqual(len(self.pc.search_journal(limit=2)), 2)

    def test_remove_entry(self):
        e1 = self.pc.add_journal_entry("Keep")
        e2 = self.pc.add_journal_entry("Remove me")
        self.assertTrue(self.pc.remove_journal_entry(e2['id']))
        self.assertEqual([e['id'] for e in self.pc.journal], [e1['id']])
        self.assertFalse(self.pc.remove_journal_entry('does-not-exist'))

    def test_journal_round_trips_via_to_from_dict(self):
        self.pc.add_journal_entry("First note", kind='note', tags=['intro'])
        self.pc.add_journal_entry("Narration line", kind='narration', source='hall')
        data = self.pc.to_dict()
        restored = PlayerCharacter.from_dict(data)
        self.assertEqual(len(restored.journal), 2)
        self.assertEqual(restored.journal[0]['text'], 'First note')
        self.assertEqual(restored.journal[0]['tags'], ['intro'])
        self.assertEqual(restored.journal[1]['kind'], 'narration')


if __name__ == '__main__':
    unittest.main()
