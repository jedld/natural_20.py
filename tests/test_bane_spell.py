import random
import unittest

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


class TestBaneSpell(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        return Session(root_path="tests/fixtures", event_manager=event_manager)

    def setUp(self):
        random.seed(7013)
        self.session = self.make_session()
        self.cleric = PlayerCharacter.load(self.session, "dwarf_cleric.yml")
        self.map = Map(self.session, "battle_sim_objects")
        self.battle = Battle(self.session, self.map)
        self.npc = self.map.entity_at(5, 5)
        self.battle.add(self.cleric, "a", position=[0, 5])
        self.battle.add(self.npc, "b")
        self.battle.start()
        self.cleric.reset_turn(self.battle)

    def test_bane_penalizes_saves(self):
        # Directly register bane on target and verify save string shows a minus term
        self.npc.register_effect('bane', object, effect=None, source=self.cleric, duration=60)
        random.seed(7015)
        roll = self.npc.save_throw('wisdom', self.battle)
        s = str(roll)
        self.assertIn('-', s)

    def test_bane_penalizes_spell_attack(self):
        # Put bane on the caster and make a ranged spell attack to ensure a minus term gets added
        self.cleric.register_effect('bane', object, effect=None, source=self.npc, duration=60)
        action = SpellAction.build(self.session, self.cleric)["next"](["guiding_bolt", 0])["next"](self.npc)
        action.resolve(self.session, self.map, {"battle": self.battle})
        attack_events = [r for r in action.result if r.get('attack_roll') is not None]
        if attack_events:
            s = str(attack_events[0]['attack_roll'])
            self.assertIn('-', s)


if __name__ == '__main__':
    unittest.main()
