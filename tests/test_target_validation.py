"""Tests for structured targeting validation issues."""

from __future__ import annotations

import unittest

import i18n

from natural20.actions.bardic_inspiration_action import BardicInspirationAction
from natural20.actions.shove_action import ShoveAction
from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.light_spell import LightSpell
from natural20.utils.target_validation import (
    TargetValidationIssue,
    evaluate_bardic_inspiration_target,
    issue,
    validation_response_payload,
)


class TestTargetValidation(unittest.TestCase):
    def setUp(self):
        i18n.set("locale", "en")
        i18n.load_path.append("tests/fixtures/locales")
        self.session = Session(root_path="tests/fixtures", event_manager=EventManager())
        self.map = Map(self.session, "battle_sim_objects")
        self.battle = Battle(self.session, self.map)
        self.bard = PlayerCharacter.load(self.session, "human_bard.yml")
        self.ally = PlayerCharacter.load(self.session, "high_elf_fighter.yml")
        self.enemy = PlayerCharacter.load(self.session, "high_elf_fighter.yml")
        self.battle.add(self.bard, "a", position=[0, 0])
        self.battle.add(self.ally, "a", position=[1, 0])
        self.battle.add(self.enemy, "b", position=[6, 5])
        self.battle.start()

    def test_issue_serializes_with_resolved_message(self):
        entry = issue("validation.targeting.self")
        payload = entry.to_dict()
        self.assertEqual(payload["key"], "validation.targeting.self")
        self.assertTrue(payload["message"])

    def test_validation_response_payload_from_action(self):
        action = BardicInspirationAction(self.session, self.bard, "bardic_inspiration")
        action.add_validation_issue("validation.targeting.self")
        payload = validation_response_payload(action)
        self.assertEqual(payload["errors"], ["validation.targeting.self"])
        self.assertEqual(len(payload["error_details"]), 1)
        self.assertEqual(payload["primary_error"], payload["error_details"][0]["message"])

    def test_bardic_inspiration_self_target_reason(self):
        action = BardicInspirationAction(self.session, self.bard, "bardic_inspiration")
        action.validate(self.map, target=self.bard)
        self.assertTrue(action.validation_failed())
        self.assertEqual(action.errors, ["validation.targeting.self"])
        payload = validation_response_payload(action)
        self.assertEqual(payload["errors"], ["validation.targeting.self"])

    def test_bardic_inspiration_deafened_target_reason(self):
        self.ally.statuses.append("deafened")
        action = BardicInspirationAction(self.session, self.bard, "bardic_inspiration")
        action.validate(self.map, target=self.ally, battle=self.battle)
        self.assertIn("validation.targeting.deafened", action.errors)

    def test_bardic_inspiration_enemy_not_valid(self):
        action = BardicInspirationAction(self.session, self.bard, "bardic_inspiration")
        action.validate(self.map, target=self.enemy, battle=self.battle)
        self.assertIn("validation.targeting.not_ally", action.errors)

    def test_bardic_inspiration_out_of_range_reason(self):
        from unittest.mock import patch

        action = BardicInspirationAction(self.session, self.bard, "bardic_inspiration")
        with patch.object(self.map, "distance", return_value=15):
            action.validate(self.map, target=self.ally, battle=self.battle)
        self.assertIn("validation.targeting.out_of_range", action.errors)
        detail = validation_response_payload(action)["error_details"][0]
        self.assertEqual(detail["params"]["range_ft"], 60)

    def test_evaluate_bardic_inspiration_target_returns_multiple_issues(self):
        issues = evaluate_bardic_inspiration_target(self.bard, self.enemy, self.battle)
        keys = [entry.key for entry in issues]
        self.assertIn("validation.targeting.not_ally", keys)

    def test_light_spell_out_of_range_coordinate_reason(self):
        spell_props = self.session.load_spell("light")
        spell = LightSpell(self.session, self.bard, "LightSpell", spell_props)
        spell.validate(self.map, target=[7, 5])
        self.assertIn("validation.targeting.out_of_range", spell.errors)

    def test_spell_action_propagates_spell_validation_issues(self):
        spell_props = self.session.load_spell("light")
        wrapper = SpellAction(self.session, self.bard, "spell")
        wrapper.spell_action = LightSpell(self.session, self.bard, "LightSpell", spell_props)
        wrapper.validate(self.map, target=self.bard)
        self.assertFalse(wrapper.validation_failed())

        wrapper.validate(self.map, target=[7, 5])
        self.assertIn("validation.targeting.out_of_range", wrapper.errors)
        self.assertEqual(
            wrapper.validation_issues[0].key,
            "validation.targeting.out_of_range",
        )

    def test_shove_records_structured_invalid_size_reason(self):
        from unittest.mock import patch

        huge = PlayerCharacter.load(self.session, "high_elf_fighter.yml")
        action = ShoveAction(self.session, self.bard, "shove")
        action.target = huge
        with patch.object(self.bard, "size_identifier", return_value=2), patch.object(
            huge, "size_identifier", return_value=5
        ):
            action.validate(self.map, target=huge)
        self.assertIn("validation.shove.invalid_target_size", action.errors)
        self.assertTrue(action.validation_failed())


if __name__ == "__main__":
    unittest.main()
