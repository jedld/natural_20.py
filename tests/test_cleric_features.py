"""Tests for the level-2 cleric class-feature additions:

- Divine domain spell auto-merge into prepared spells.
- Domain-specific class features gated by cleric level.
- Channel Divinity counter wired through Turn Undead.
- Disciple of Life bonus to Cure Wounds healing.
"""

import random
import unittest

from natural20.actions.attack_action import AttackAction  # noqa: F401  (keeps imports parallel to other test modules)
from natural20.actions.spell_action import SpellAction
from natural20.actions.turn_undead_action import TurnUndeadAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.npc import Npc
from natural20.player_character import PlayerCharacter
from natural20.session import Session


class TestClericFeatures(unittest.TestCase):
    def setUp(self):
        random.seed(7000)
        event_manager = EventManager()
        event_manager.standard_cli()
        self.session = Session(root_path="tests/fixtures", event_manager=event_manager)
        self.map = Map(self.session, "battle_sim")
        self.battle = Battle(self.session, self.map)
        self.cleric = PlayerCharacter.load(self.session, "dwarf_cleric.yml")
        self.skeleton = Npc.load(self.session, "npcs/skeleton.yml")
        self.battle.add(self.cleric, "a", position="spawn_point_1")
        self.battle.add(self.skeleton, "b", position="spawn_point_3")
        self.cleric.reset_turn(self.battle)

    # ---------- domain-spell auto-merge ----------

    def test_domain_spells_auto_merged(self):
        prepared = self.cleric.prepared_spells()
        # Cure wounds is in the explicit prepared list; bless is provided by the
        # life-domain auto-merge for level_1; spiritual_weapon comes from level_3.
        self.assertIn("cure_wounds", prepared)
        self.assertIn("bless", prepared)
        self.assertIn("spiritual_weapon", prepared)

    # ---------- domain features gated by level ----------

    def test_disciple_of_life_present_for_life_cleric(self):
        self.assertTrue(self.cleric.class_feature("disciple_of_life"))

    def test_destroy_undead_not_present_below_level_5(self):
        self.assertFalse(self.cleric.class_feature("destroy_undead"))

    def test_divine_intervention_not_present_below_level_10(self):
        self.assertFalse(self.cleric.class_feature("divine_intervention"))

    def test_channel_divinity_present_at_level_2(self):
        self.assertTrue(self.cleric.class_feature("channel_divinity"))
        self.assertTrue(self.cleric.class_feature("channel_divinity_turn_undead"))

    # ---------- Turn Undead ----------

    def test_turn_undead_action_available(self):
        self.assertTrue(TurnUndeadAction.can(self.cleric, self.battle))

    def test_turn_undead_consumes_channel_divinity(self):
        self.assertEqual(self.cleric.channel_divinity_count, 1)
        action = TurnUndeadAction.build(self.session, self.cleric)
        action.resolve(self.session, self.map, {"battle": self.battle})
        # At least one result item (skeleton in range or no-target placeholder)
        self.assertGreaterEqual(len(action.result), 1)
        self.battle.commit(action)
        self.assertEqual(self.cleric.channel_divinity_count, 0)

    def test_turn_undead_fails_when_no_channel_divinity(self):
        self.cleric.channel_divinity_count = 0
        self.assertFalse(TurnUndeadAction.can(self.cleric, self.battle))

    def test_short_rest_refills_channel_divinity(self):
        self.cleric.channel_divinity_count = 0
        self.cleric.short_rest_for_cleric(self.battle)
        self.assertEqual(self.cleric.channel_divinity_count, 1)

    # ---------- Disciple of Life healing bonus ----------

    def test_disciple_of_life_bonus_value(self):
        # 2 + spell level for any leveled healing spell.
        self.assertEqual(self.cleric.disciple_of_life_bonus(1), 3)
        self.assertEqual(self.cleric.disciple_of_life_bonus(3), 5)
        # Cantrip / level 0 healing receives no bonus.
        self.assertEqual(self.cleric.disciple_of_life_bonus(0), 0)

    def test_cure_wounds_applies_disciple_of_life_bonus(self):
        random.seed(9001)
        # Drop cleric well below max so the bonus actually moves the needle.
        max_hp = self.cleric.max_hp()
        self.cleric.attributes["hp"] = 1
        action = SpellAction.build(self.session, self.cleric)["next"](
            ["cure_wounds", 0]
        )["next"](self.cleric)
        action.resolve(self.session, self.map, {"battle": self.battle})
        item = action.result[0]
        self.battle.commit(action)
        self.assertEqual(item["type"], "spell_heal")
        self.assertEqual(item["disciple_of_life_bonus"], 3)
        self.assertEqual(item["total_heal"], item["heal_value"] + 3)
        # Final HP equals 1 + total_heal capped at max.
        expected_hp = min(max_hp, 1 + item["total_heal"])
        self.assertEqual(self.cleric.hp(), expected_hp)


if __name__ == "__main__":
    unittest.main()
