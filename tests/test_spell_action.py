import unittest
from natural20.actions.spell_action import SpellAction
from natural20.utils.utils import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter

from natural20.map import Map
from natural20.battle import Battle
from natural20.utils.action_builder import autobuild
from natural20.map_renderer import MapRenderer
from natural20.weapons import target_advantage_condition
import random
import pdb

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

    def setupMageArmor(self):
        self.assertEqual(self.entity.armor_class(), 12)
        action = SpellAction.build(self.session, self.entity)['next'](['mage_armor', 0])['next'](self.entity)['next']()
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['mage_armor'])
        self.battle.commit(action)
        self.assertEqual(self.entity.armor_class(), 15)
        return action

    def test_mage_armor(self):
        action = self.setupMageArmor()
        self.assertTrue(self.entity.dismiss_effect(action.spell_action))
        self.assertEqual(self.entity.armor_class(), 12)
    
    def test_equip_armor_cancels_effect(self):
        self.setupMageArmor()
        self.assertEqual(self.entity.armor_class(), 15)
        self.entity.equip('studded_leather', ignore_inventory=True)
        self.assertEqual(self.entity.armor_class(), 12)

    def test_chill_touch(self):
        self.assertEqual(self.npc.hp(), 7)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['chill_touch', 0])['next'](self.npc)['next']()
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['spell_damage', 'chill_touch'])
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 0)
        self.assertTrue(self.npc.has_spell_effect('chill_touch'))

        # target cannot heal until effect ends
        self.npc.heal(100)
        self.assertEqual(self.npc.hp(), 0)

        # drop effect until next turn
        self.entity.reset_turn(self.battle)
        self.npc.heal(100)
        self.assertNotEqual(self.npc.hp(), 3)

    def test_chill_touch_undead(self):
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[5, 5])
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['chill_touch', 0])['next'](self.npc)['next']()
        action.resolve(self.session, self.battle_map, { "battle" : self.battle})
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 5)
        self.assertEqual(target_advantage_condition(self.battle, self.npc, self.entity, None), [-1, [[], ['chill_touch_disadvantage']]])

    def test_expeditious_retreat(self):
        action = SpellAction.build(self.session, self.entity)['next'](['expeditious_retreat', 0])['next']()
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['expeditious_retreat'])
        self.battle.commit(action)
        self.assertIn('dash_bonus', [a.action_type for a in self.entity.available_actions(self.session, self.battle)])

    def autobuild_test(self):
        auto_build_actions = autobuild(self.session, SpellAction, self.entity, self.battle)
        pdb.set_trace()
        self.assertEqual(len(auto_build_actions), 1)


if __name__ == '__main__':
    unittest.main()
