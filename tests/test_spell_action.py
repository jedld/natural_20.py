import unittest
from natural20.actions.spell_action import SpellAction
from natural20.utils.utils import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.npc import Npc
from natural20.map import Map
from natural20.battle import Battle
from natural20.map_renderer import MapRenderer
import random

class TestSpellAction(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=event_manager)
    
    def setUp(self):
        random.seed(7000)
        self.session = self.make_session()
        self.entity = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.battle_map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.battle_map)
        self.npc = self.battle_map.entity_at(5, 5)
        self.battle.add(self.entity, 'a', position=[0, 5])
        self.entity.reset_turn(self.battle)

    def test_firebolt(self):
        self.assertEqual(self.npc.hp(), 7)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['firebolt',0])['next'](self.npc)['next']()
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['spell_damage'])
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 0)

    def test_shocking_grasp(self):
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        self.npc.reset_turn(self.battle)
        random.seed(7000)
        print(MapRenderer(self.battle_map).render())
        build = SpellAction.build(self.session, self.entity)['next'](['shocking_grasp', 0])
        build = build['next'](self.npc)
        action = build['next']()
        action.resolve(self.session, self.battle_map, { "battle" : self.battle})
        self.assertEqual([s['type'] for s in action.result], ['spell_damage', 'shocking_grasp'])
        self.assertTrue(self.npc.has_reaction(self.battle))
        self.battle.commit(action)
        self.assertFalse(self.npc.has_reaction(self.battle))
        self.assertEqual(self.npc.hp(), 12)

    # Add more test cases for other spells...

if __name__ == '__main__':
    unittest.main()
