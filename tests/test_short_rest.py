"""Tests for the short-rest pipeline (engine layer)."""
import unittest
from unittest.mock import patch

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.session import Session


def _make_session():
    event_manager = EventManager()
    return Session(root_path='tests/fixtures', event_manager=event_manager)


class TestShortRest(unittest.TestCase):
    def setUp(self):
        self.session = _make_session()
        self.battle = Battle(self.session, None)

    # ------------------------------------------------------------------
    # Combat guard
    # ------------------------------------------------------------------
    def test_short_rest_blocked_during_combat(self):
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(fighter, 'a')
        self.battle.start()
        fighter.take_damage(5, session=self.session)
        with self.assertRaises(ValueError):
            fighter.short_rest(self.battle)

    def test_short_rest_force_overrides_combat_guard(self):
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(fighter, 'a')
        self.battle.start()
        fighter.take_damage(5, session=self.session)
        # Should not raise and should refresh second wind etc.
        fighter.short_rest(self.battle, force=True)

    def test_short_rest_without_battle(self):
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        fighter.take_damage(3, session=self.session)
        # No battle context means no combat -> always allowed.
        fighter.short_rest(None)

    # ------------------------------------------------------------------
    # Per-class hooks fire
    # ------------------------------------------------------------------
    def test_fighter_second_wind_resets_on_short_rest(self):
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        fighter.second_wind_count = 0
        fighter.short_rest(None)
        self.assertEqual(fighter.second_wind_count, 1)

    def test_warlock_pact_slots_recharge_on_short_rest(self):
        warlock = PlayerCharacter.load(self.session, 'human_warlock.yml')
        slots = warlock.spell_slots['warlock']
        # Drain every leveled slot.
        for level in list(slots.keys()):
            if level > 0:
                slots[level] = 0
        warlock.short_rest(None)
        refilled = warlock.spell_slots['warlock']
        self.assertTrue(any(refilled[lvl] > 0 for lvl in refilled if lvl > 0),
                        f"warlock slots not refilled: {refilled}")

    def test_short_rest_event_fires(self):
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        seen = []
        fighter.event_manager.register_event_listener(
            ['short_rest'], lambda evt: seen.append(evt))
        fighter.short_rest(None)
        self.assertEqual(len(seen), 1)
        self.assertIs(seen[0]['source'], fighter)

    # ------------------------------------------------------------------
    # Hit-die mechanics
    # ------------------------------------------------------------------
    def test_use_hit_die_decrements_pool_and_heals(self):
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        fighter.take_damage(10, session=self.session)
        before_hp = fighter.hp()
        before_dice = dict(fighter.hit_die())
        die_type = next(iter(before_dice))
        fighter.use_hit_die(die_type)
        self.assertEqual(fighter.hit_die()[die_type], before_dice[die_type] - 1)
        self.assertGreater(fighter.hp(), before_hp)

    def test_short_rest_revives_stable_unconscious(self):
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        fighter.take_damage(fighter.hp() + 5, session=self.session)
        # Mark stable so revival path triggers (no death-save bookkeeping).
        if 'stable' not in fighter.statuses:
            fighter.statuses.append('stable')
        if not fighter.unconscious() and 'unconscious' not in fighter.statuses:
            fighter.statuses.append('unconscious')
        # Spend any remaining hit dice during the rest.
        fighter.short_rest(None)
        self.assertGreaterEqual(fighter.hp(), 1)
        self.assertFalse(fighter.unconscious())

    # ------------------------------------------------------------------
    # Long rest hit-die regen + class hook
    # ------------------------------------------------------------------
    def test_long_rest_restores_hit_dice(self):
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        die_type = next(iter(fighter.hit_die()))
        fighter._current_hit_die[die_type] = 0
        fighter.long_rest()
        self.assertGreaterEqual(fighter._current_hit_die[die_type], 1)

    def test_long_rest_event_fires(self):
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        seen = []
        fighter.event_manager.register_event_listener(
            ['long_rest'], lambda evt: seen.append(evt))
        fighter.long_rest()
        self.assertEqual(len(seen), 1)


class TestWizardArcaneRecovery(unittest.TestCase):
    def setUp(self):
        self.session = _make_session()
        self.battle = Battle(self.session, None)

    def test_arcane_recovery_consumes_budget_and_refills_slots(self):
        wizard = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.battle.add(wizard, 'a')
        # Battle.add does not start combat, so the guard is not triggered.

        # Drain a 1st-level slot so there is room to recover.
        wiz_slots = wizard.spell_slots['wizard']
        wiz_slots[1] = 0

        picks = [1]  # ask for one level-1 slot back

        class _Controller:
            def __init__(self, picks):
                self.picks = list(picks)
                self.calls = []

            def arcane_recovery_ui(self, entity, available_levels):
                self.calls.append(list(available_levels))
                if not self.picks:
                    return None
                return self.picks.pop(0)

        controller = _Controller(picks)
        with patch.object(self.battle, 'controller_for', return_value=controller):
            wizard.short_rest(self.battle)

        self.assertEqual(wiz_slots[1], 1)
        self.assertEqual(wizard.arcane_recovery, 0)
        # Long rest should rearm arcane recovery.
        wizard.long_rest()
        self.assertEqual(wizard.arcane_recovery, 1)


if __name__ == '__main__':
    unittest.main()
