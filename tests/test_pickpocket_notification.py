"""Tests for natural20/utils/pickpocket_notification.py – NPC pickpocket notification generation."""

import unittest

from natural20.utils.pickpocket_notification import (
    pickpocket_attempt_note,
    pickpocket_success_note,
    pickpocket_failed_note,
    pickpocket_victim_caught_note,
    pc_pickpocket_detected_message,
    multiple_pickpocket_attempts_note,
)
from unittest.mock import MagicMock


class TestPickpocketAttemptNote(unittest.TestCase):
    """Test pickpocket_attempt_note for different detection scenarios."""

    def test_seen_successful(self):
        npc = MagicMock(name='witness_goblin')
        picker = MagicMock(name='thief_goblin')
        target = MagicMock(name='victim_goblin')

        note = pickpocket_attempt_note(
            npc, picker, target, 'copper coin',
            success=True, detection_type='seen', can_see=True
        )

        self.assertIn('PICKPOCKET ATTEMPT:', note)
        self.assertIn('successfully pickpocket', note)
        self.assertIn('copper coin', note)
        self.assertIn('unaware', note.lower())

    def test_seen_failed(self):
        npc = MagicMock(name='witness_goblin')
        picker = MagicMock(name='thief_goblin')
        target = MagicMock(name='victim_goblin')

        note = pickpocket_attempt_note(
            npc, picker, target, 'dagger',
            success=False, detection_type='seen', can_see=True
        )

        self.assertIn('PICKPOCKET ATTEMPT:', note)
        self.assertIn('failed', note.lower())
        self.assertIn('noticed', note.lower())

    def test_heard_successful(self):
        npc = MagicMock(name='witness_goblin')
        picker = MagicMock(name='thief_goblin')
        target = MagicMock(name='victim_goblin')

        note = pickpocket_attempt_note(
            npc, picker, target, 'ring',
            success=True, detection_type='heard', can_see=False
        )

        self.assertIn('commotion', note.lower())
        self.assertIn('suspect', note.lower())

    def test_heard_failed(self):
        npc = MagicMock(name='witness_goblin')
        picker = MagicMock(name='thief_goblin')
        target = MagicMock(name='victim_goblin')

        note = pickpocket_attempt_note(
            npc, picker, target, 'gold piece',
            success=False, detection_type='heard', can_see=False
        )

        self.assertIn('raised voices', note.lower())
        self.assertIn('failed', note.lower())


class TestPickpocketSuccessNote(unittest.TestCase):
    """Test pickpocket_success_note for successful (undetected by target) thefts."""

    def test_seen_successful(self):
        npc = MagicMock(name='witness_goblin')
        picker = MagicMock(name='thief_goblin')
        target = MagicMock(name='victim_goblin')

        note = pickpocket_success_note(
            npc, picker, target, 'copper coin', can_see=True
        )

        self.assertIn('[OBSERVATION]', note)
        self.assertIn('skillfully lift', note.lower())
        self.assertIn('unaware', note.lower())

    def test_not_seen_successful(self):
        npc = MagicMock(name='witness_goblin')
        picker = MagicMock(name='thief_goblin')
        target = MagicMock(name='victim_goblin')

        note = pickpocket_success_note(
            npc, picker, target, 'ring', can_see=False
        )

        self.assertIn('[SOUND]', note)
        self.assertIn('silence', note.lower())


class TestPickpocketFailedNote(unittest.TestCase):
    """Test pickpocket_failed_note for detected (failed) pickpocket attempts."""

    def test_seen_failed(self):
        npc = MagicMock(name='witness_goblin')
        picker = MagicMock(name='thief_goblin')
        target = MagicMock(name='victim_goblin')

        note = pickpocket_failed_note(
            npc, picker, target, 'dagger', can_see=True
        )

        self.assertIn('[ALERT]', note)
        self.assertIn('fail', note.lower())
        self.assertIn('noticed', note.lower())

    def test_not_seen_failed(self):
        npc = MagicMock(name='witness_goblin')
        picker = MagicMock(name='thief_goblin')
        target = MagicMock(name='victim_goblin')

        note = pickpocket_failed_note(
            npc, picker, target, 'gold piece', can_see=False
        )

        self.assertIn('[SOUND]', note)
        self.assertIn('raised voices', note.lower())


class TestMultiplePickpocketAttemptsNote(unittest.TestCase):
    """Test multiple_pickpocket_attempts_note for repeated offenses."""

    def test_first_attempt(self):
        npc = MagicMock(name='witness_goblin')
        picker = MagicMock(name='thief_goblin')
        target = MagicMock(name='victim_goblin')

        note = multiple_pickpocket_attempts_note(
            npc, picker, target, 'copper coin',
            success=False, previous_attempts=0, can_see=True
        )

        self.assertIn('REPEATED PICKPOCKET', note)
        # Should not mention "another" when previous_attempts=0
        self.assertNotIn('another', note.lower())

    def test_subsequent_attempt(self):
        npc = MagicMock(name='witness_goblin')
        picker = MagicMock(name='thief_goblin')
        target = MagicMock(name='victim_goblin')

        note = multiple_pickpocket_attempts_note(
            npc, picker, target, 'dagger',
            success=True, previous_attempts=2, can_see=True
        )

        self.assertIn('REPEATED PICKPOCKET', note)
        self.assertIn('another', note.lower())
        # previous_attempts=2 means "3 suspicious act(s)" (2+1)
        self.assertIn('3 suspicious', note.lower())


class TestPickpocketVictimCaughtNote(unittest.TestCase):
    def test_victim_caught_note_prompts_immediate_reaction(self):
        victim = MagicMock(name='merchant')
        picker = MagicMock(name='thief')

        note = pickpocket_victim_caught_note(victim, picker, 'ring')

        self.assertIn('PICKPOCKET CAUGHT:', note)
        self.assertIn('ring', note)
        self.assertIn('Decide whether to react', note)
        self.assertIn('[GO_HOSTILE]', note)


class TestPcPickpocketDetectedMessage(unittest.TestCase):
    def test_failed_attempt_includes_target(self):
        pc = MagicMock(name='pc')
        target = MagicMock(name='merchant')
        target.label.return_value = 'Merchant'

        message = pc_pickpocket_detected_message(
            pc, target, 'gold coin', [], success=False,
        )

        self.assertIn('Pickpocket failed', message)
        self.assertIn('Merchant', message)
        self.assertIn('gold coin', message)

    def test_success_with_witnesses_warns_pc(self):
        pc = MagicMock(name='pc')
        target = MagicMock(name='merchant')
        target.label.return_value = 'Merchant'

        message = pc_pickpocket_detected_message(
            pc, target, 'dagger', ['Bystander'], success=True,
        )

        self.assertIn('Bystander', message)
        self.assertIn('succeeded', message.lower())


if __name__ == '__main__':
    unittest.main()
