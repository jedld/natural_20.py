"""RAW shove: Attack-action special melee attack (2014 contest / 2024 save)."""

from unittest.mock import MagicMock
import unittest

import i18n

from natural20.actions.shove_action import PushAction, ShoveAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.ruleset.ruleset_2024 import Ruleset2024
from natural20.session import Session


def _roll(value):
    roll = MagicMock()
    roll.result.return_value = value
    roll.__str__.return_value = str(value)
    return roll


class TestShoveAction(unittest.TestCase):
    def setUp(self):
        i18n.set("locale", "en")
        i18n.load_path.append("tests/fixtures/locales")
        self.session = Session(root_path="tests/fixtures", event_manager=EventManager())
        self.map = Map(self.session, "maps/empty_map")
        self.battle = Battle(self.session, self.map)
        self.shover = PlayerCharacter.load(self.session, "high_elf_fighter.yml")
        self.target = PlayerCharacter.load(self.session, "human_bard.yml")
        self.blocker = PlayerCharacter.load(self.session, "dwarf_cleric.yml")
        self.battle.add(self.shover, "a", position=(1, 1), token="S")
        self.battle.add(self.target, "b", position=(2, 1), token="T")
        self.battle.start()
        self.battle.set_current_turn(self.shover)
        self.shover.reset_turn(self.battle)
        self.target.reset_turn(self.battle)

    def _commit(self, action):
        action.resolve(self.session, self.map, {"battle": self.battle})
        for item in action.result:
            ShoveAction.apply(self.battle, item, self.session)

    def _win_contest(self, action):
        action.target = self.target
        self.shover.athletics_check = lambda *a, **k: _roll(18)
        self.target.athletics_check = lambda *a, **k: _roll(5)
        self.target.acrobatics_check = lambda *a, **k: _roll(5)
        self._commit(action)

    def test_available_actions_offer_prone_and_push(self):
        names = [str(a) for a in self.shover.available_actions(self.session, self.battle)]
        self.assertIn("Shove", names)
        self.assertIn("Push", names)
        shove = next(a for a in self.shover.available_actions(self.session, self.battle) if isinstance(a, ShoveAction) and not isinstance(a, PushAction))
        push = next(a for a in self.shover.available_actions(self.session, self.battle) if isinstance(a, PushAction))
        self.assertTrue(shove.knock_prone)
        self.assertFalse(push.knock_prone)

    def test_knock_prone_on_success(self):
        action = ShoveAction(self.session, self.shover, "shove")
        self._win_contest(action)
        self.assertTrue(self.target.prone())
        self.assertEqual(tuple(self.map.entity_or_object_pos(self.target)), (2, 1))

    def test_push_five_feet_on_success(self):
        action = PushAction(self.session, self.shover, "push")
        self._win_contest(action)
        self.assertFalse(self.target.prone())
        self.assertEqual(tuple(self.map.entity_or_object_pos(self.target)), (3, 1))

    def test_tie_goes_to_defender(self):
        action = ShoveAction(self.session, self.shover, "shove")
        action.target = self.target
        self.shover.athletics_check = lambda *a, **k: _roll(12)
        self.target.athletics_check = lambda *a, **k: _roll(12)
        self.target.acrobatics_check = lambda *a, **k: _roll(12)
        self._commit(action)
        self.assertFalse(self.target.prone())
        self.assertEqual(tuple(self.map.entity_or_object_pos(self.target)), (2, 1))

    def test_size_limit_one_size_larger(self):
        action = ShoveAction(self.session, self.shover, "shove")
        action.target = self.target
        self.target.size_identifier = lambda: self.shover.size_identifier() + 2
        action.validate(self.map, target=self.target)
        self.assertIn("validation.shove.invalid_target_size", action.errors)
        action.resolve(self.session, self.map, {"battle": self.battle})
        self.assertEqual(action.result, [])

    def test_out_of_reach(self):
        self.map.move_to(self.target, 4, 1, self.battle)
        action = ShoveAction(self.session, self.shover, "shove")
        action.target = self.target
        action.validate(self.map, target=self.target)
        self.assertIn("validation.targeting.out_of_range", action.errors)

    def test_cannot_target_self(self):
        action = ShoveAction(self.session, self.shover, "shove")
        action.validate(self.map, target=self.shover)
        self.assertIn("validation.targeting.self", action.errors)

    def test_blocked_push_does_not_knock_prone(self):
        self.battle.add(self.blocker, "a", position=(3, 1), token="B")
        action = PushAction(self.session, self.shover, "push")
        self._win_contest(action)
        self.assertFalse(self.target.prone())
        self.assertEqual(tuple(self.map.entity_or_object_pos(self.target)), (2, 1))

    def test_incapacitated_target_auto_fails(self):
        self.target.statuses.append("incapacitated")
        action = ShoveAction(self.session, self.shover, "shove")
        action.target = self.target
        self._commit(action)
        self.assertTrue(self.target.prone())

    def test_consumes_action(self):
        before = self.shover.total_actions(self.battle)
        action = ShoveAction(self.session, self.shover, "shove")
        self._win_contest(action)
        self.assertEqual(self.shover.total_actions(self.battle), before - 1)


class TestShoveAction2024(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path="tests/fixtures", event_manager=EventManager())
        self.session.ruleset = Ruleset2024()
        self.map = Map(self.session, "maps/empty_map")
        self.battle = Battle(self.session, self.map)
        self.shover = PlayerCharacter.load(self.session, "high_elf_fighter.yml")
        self.target = PlayerCharacter.load(self.session, "human_bard.yml")
        self.battle.add(self.shover, "a", position=(1, 1), token="S")
        self.battle.add(self.target, "b", position=(2, 1), token="T")
        self.battle.start()
        self.battle.set_current_turn(self.shover)
        self.shover.reset_turn(self.battle)

    def test_failed_save_knocks_prone(self):
        action = ShoveAction(self.session, self.shover, "shove")
        action.target = self.target
        dc = 8 + self.shover.str_mod() + self.shover.proficiency_bonus()
        self.target.save_throw = lambda *a, **k: _roll(dc - 1)
        action.resolve(self.session, self.map, {"battle": self.battle})
        for item in action.result:
            ShoveAction.apply(self.battle, item, self.session)
        self.assertTrue(self.target.prone())
        self.assertEqual(action.result[0]["save_dc"], dc)

    def test_save_tie_resists_shove(self):
        action = PushAction(self.session, self.shover, "push")
        action.target = self.target
        dc = 8 + self.shover.str_mod() + self.shover.proficiency_bonus()
        self.target.save_throw = lambda *a, **k: _roll(dc)
        action.resolve(self.session, self.map, {"battle": self.battle})
        for item in action.result:
            ShoveAction.apply(self.battle, item, self.session)
        self.assertEqual(tuple(self.map.entity_or_object_pos(self.target)), (2, 1))
        self.assertFalse(action.result[0]["success"])


if __name__ == "__main__":
    unittest.main()
