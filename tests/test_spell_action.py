import unittest
from natural20.actions.spell_action import SpellAction
from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter

from natural20.map import Map
from natural20.battle import Battle
from natural20.utils.action_builder import autobuild
from natural20.map_renderer import MapRenderer
from natural20.weapons import target_advantage_condition
from natural20.utils.spell_attack_util import evaluate_spell_attack
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
        random.seed(7002)
        self.assertEqual(self.npc.hp(), 6)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['firebolt',0])['next'](self.npc)
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['spell_damage'])
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 0)

    def test_ranged_spell_attack_with_disadvantage(self):
        self.assertEqual(self.npc.hp(), 6)
        self.npc2 = self.session.npc('skeleton')
        self.battle.add(self.npc2, 'b', position=[1, 6])
        print(MapRenderer(self.battle_map).render())
        firebolt_spell = self.session.load_spell('firebolt')
        _, _, advantage_mod, _, _ = evaluate_spell_attack(self.battle, self.entity, self.npc, firebolt_spell)
        self.assertEqual(advantage_mod, -1)

    def test_shocking_grasp(self):
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        self.npc.reset_turn(self.battle)
        random.seed(7000)
        print(MapRenderer(self.battle_map).render())
        build = SpellAction.build(self.session, self.entity)['next'](['shocking_grasp', 0])
        action = build['next'](self.npc)
        action.resolve(self.session, self.battle_map, { "battle" : self.battle})
        self.assertEqual([s['type'] for s in action.result], ['spell_damage', 'shocking_grasp'])
        self.assertTrue(self.npc.has_reaction(self.battle))
        self.battle.commit(action)
        self.assertFalse(self.npc.has_reaction(self.battle))
        self.assertEqual(self.npc.hp(), 12)

    def setupMageArmor(self):
        self.assertEqual(self.entity.armor_class(), 12)
        action = SpellAction.build(self.session, self.entity)['next'](['mage_armor', 0])['next'](self.entity)
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
        random.seed(1002)
        self.assertEqual(self.npc.hp(), 6)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['chill_touch', 0])['next'](self.npc)
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
        random.seed(1002)
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[5, 5])
        self.assertEqual(self.npc.hp(), 13)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['chill_touch', 0])['next'](self.npc)
        action.resolve(self.session, self.battle_map, { "battle" : self.battle})
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 6)
        self.assertEqual(target_advantage_condition(self.battle, self.npc, self.entity, None), [-1, [[], ['chill_touch_disadvantage']]])

    def test_expeditious_retreat(self):
        action = SpellAction.build(self.session, self.entity)['next'](['expeditious_retreat', 0])
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['expeditious_retreat'])
        self.battle.commit(action)
        self.assertIn('dash_bonus', [a.action_type for a in self.entity.available_actions(self.session, self.battle)])

    def test_ray_of_frost(self):
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        self.npc.reset_turn(self.battle)
        random.seed(1002)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['ray_of_frost', 0])['next'](self.npc)
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['spell_damage', 'ray_of_frost'])
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 9)
        self.assertEqual(self.npc.speed(), 20)
        self.entity.reset_turn(self.battle)
        self.assertEqual(self.npc.speed(), 30)

    def test_compute_hit_probability(self):
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        self.npc.reset_turn(self.battle)

        action = SpellAction.build(self.session, self.entity)['next'](['ray_of_frost', 0])['next'](self.npc)
        self.assertAlmostEqual(action.compute_hit_probability(self.battle), 0.49)
        self.assertAlmostEqual(action.avg_damage(self.battle), 4.5)

        action = SpellAction.build(self.session, self.entity)['next'](['firebolt', 0])['next'](self.npc)
        self.assertAlmostEqual(action.compute_hit_probability(self.battle), 0.49)
        self.assertAlmostEqual(action.avg_damage(self.battle), 5.5)

    def autobuild_test(self):
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        auto_build_actions = autobuild(self.session, SpellAction, self.entity, self.battle)
        self.assertEqual(len(auto_build_actions), 3)
        self.assertEqual([str(a) for a in  auto_build_actions], ['SpellAction: firebolt',
                                              'SpellAction: mage_armor',
                                              'SpellAction: magic_missile'])

        self.assertEqual(self.entity.armor_class(), 12)
        # must be a valid action
        for a in auto_build_actions:
            a.resolve(self.session, self.battle_map, { "battle": self.battle})
            self.battle.commit(a)
        # mage armor should take effect
        self.assertEqual(self.entity.armor_class(), 15)

if __name__ == '__main__':
    unittest.main()
