import unittest

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


class TestGuidanceSpell(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        return Session(root_path="tests/fixtures", event_manager=event_manager)

    def setUp(self):
        self.session = self.make_session()
        self.cleric = PlayerCharacter.load(self.session, "dwarf_cleric.yml")
        self.map = Map(self.session, "battle_sim_objects")
        self.battle = Battle(self.session, self.map)
        self.npc = self.map.entity_at(5, 5)
        self.battle.add(self.cleric, "a", position=[0, 5])
        self.battle.add(self.npc, "b")
        self.battle.start()
        self.cleric.reset_turn(self.battle)

    def cast_guidance_on(self, target):
        action = SpellAction.build(self.session, self.cleric)["next"](["guidance", 0])["next"](target)
        resolved = action.resolve(self.session, self.map, {"battle": self.battle})
        for item in resolved.result:
            SpellAction.apply(self.battle, item, self.session)

    def test_guidance_triggers_on_failed_ability_check(self):
        self.cast_guidance_on(self.cleric)
        self.assertTrue(self.cleric.has_effect('guidance'))

        DieRoll.fudge(2, die_sides=20)
        DieRoll.fudge(4, die_sides=4)

        roll = self.cleric.athletics_check(self.battle)
        result = roll.result() >= 10

        self.assertIn('guidance_bonus', roll.metadata)
        self.assertEqual(roll.metadata['guidance_bonus'], 4)
        self.assertFalse(self.cleric.has_effect('guidance'))
        self.assertFalse(result)

    def test_guidance_not_consumed_on_successful_check(self):
        self.cast_guidance_on(self.cleric)
        self.assertTrue(self.cleric.has_effect('guidance'))

        DieRoll.fudge(19, die_sides=20)

        roll = self.cleric.athletics_check(self.battle)
        result = roll.result() >= 5

        self.assertNotIn('guidance_bonus', roll.metadata)
        self.assertTrue(self.cleric.has_effect('guidance'))
        self.assertTrue(result)

    def test_guidance_applies_for_contested_checks(self):
        self.cast_guidance_on(self.cleric)
        self.assertTrue(self.cleric.has_effect('guidance'))

        DieRoll.fudge(15, die_sides=20)
        strength_roll = self.npc.athletics_check(self.battle)

        DieRoll.fudge(3, die_sides=20)
        DieRoll.fudge(3, die_sides=4)
        contested_roll = self.cleric.acrobatics_check(self.battle)

        _ = strength_roll.result() >= contested_roll.result()

        self.assertIn('guidance_bonus', contested_roll.metadata)
        self.assertEqual(contested_roll.metadata['guidance_bonus'], 3)
        self.assertFalse(self.cleric.has_effect('guidance'))


if __name__ == '__main__':
    unittest.main()
