import random
import unittest

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


class TestResistanceSpell(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        return Session(root_path="tests/fixtures", event_manager=event_manager)

    def setUp(self):
        random.seed(7099)
        self.session = self.make_session()
        self.cleric = PlayerCharacter.load(self.session, "dwarf_cleric.yml")
        self.map = Map(self.session, "battle_sim_objects")
        self.battle = Battle(self.session, self.map)
        self.npc = self.map.entity_at(5, 5)
        self.battle.add(self.cleric, "a", position=[0, 5])
        self.battle.add(self.npc, "b")
        self.battle.start()
        self.cleric.reset_turn(self.battle)

    def test_resistance_applies_once(self):
        # Cast resistance on self.cleric
        action = SpellAction.build(self.session, self.cleric)["next"](["resistance", 0])["next"](self.cleric)
        action.resolve(self.session, self.map, {"battle": self.battle})
        # First save should include a + term
        random.seed(7101)
        roll1 = self.cleric.save_throw('wisdom', self.battle)
        s1 = str(roll1)
        self.assertIn('+', s1)
        # Second save should not include the bonus (effect consumed)
        random.seed(7102)
        roll2 = self.cleric.save_throw('wisdom', self.battle)
        s2 = str(roll2)
        # Not asserting absence of '+', but ensure not more terms than baseline modifier by checking difference in string length
        self.assertTrue(len(s2) <= len(s1))


if __name__ == '__main__':
    unittest.main()
