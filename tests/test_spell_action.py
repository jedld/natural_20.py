import unittest
from natural20.actions.spell_action import SpellAction
from natural20.actions.find_familiar_action import FindFamiliarAction
from natural20.actions.summon_familiar_action import SummonFamiliarAction
from natural20.actions.attack_action import AttackAction
from natural20.spell.shield_spell import ShieldSpell
from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.die_roll import DieRoll
from natural20.controller import Controller
from natural20.action import AsyncReactionHandler

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
        self.battle.start()
        self.entity.reset_turn(self.battle)
        DieRoll.die_rolls().clear()

    def test_firebolt(self):
        random.seed(7002)
        self.assertEqual(self.npc.hp(), 9)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['firebolt',0])['next'](self.npc)
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['spell_damage'])
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 0)

    def test_ranged_spell_attack_with_disadvantage(self):
        self.assertEqual(self.npc.hp(), 9)
        self.npc2 = self.session.npc('skeleton')
        self.battle.add(self.npc2, 'b', position=[1, 6])
        print(MapRenderer(self.battle_map).render())
        firebolt_spell = self.session.load_spell('firebolt')
        _, _, advantage_mod, _, _, _ = evaluate_spell_attack(self.battle, self.entity, self.npc, firebolt_spell)
        self.assertEqual(advantage_mod, -1)

    def test_shocking_grasp(self):
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        self.npc.reset_turn(self.battle)
        random.seed(7002)
        print(MapRenderer(self.battle_map).render())
        build = SpellAction.build(self.session, self.entity)['next'](['shocking_grasp', 0])
        action = build['next'](self.npc)
        DieRoll.die_rolls().clear()
        self.battle.action(action)
        self.assertEqual(list(DieRoll.die_rolls())[0].advantage, False)
        self.assertEqual([s['type'] for s in action.result], ['spell_damage', 'shocking_grasp'])
        self.assertTrue(self.npc.has_reaction(self.battle))
        self.battle.commit(action)
        self.assertFalse(self.npc.has_reaction(self.battle))
        self.assertEqual(self.npc.hp(), 12)

    def test_shocking_grasp_metallic(self):
        self.npc = self.session.npc('hobgoblin')
        self.assertTrue(self.npc.equipped_metallic_armor())
        self.battle.add(self.npc, 'b', position=[0, 6])
        self.npc.reset_turn(self.battle)
        random.seed(7002)
        print(MapRenderer(self.battle_map).render())

        action = SpellAction.build(self.session, self.entity)['next'](['shocking_grasp', 0])['next'](self.npc)
        DieRoll.die_rolls().clear()
        self.battle.action(action)
        self.assertEqual(list(DieRoll.die_rolls())[0].advantage, True)
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 10)


    def setupMageArmor(self):
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

    def test_mage_armor_cast_again(self):
        action = self.setupMageArmor()
        self.entity.reset_turn(self.battle)
        self.setupMageArmor()
        self.assertEqual(self.entity.armor_class(), 15)
        current_effects = [str(e['effect']) for e in self.entity.current_effects()]
        self.assertEqual(current_effects, ['mage_armor'])
    
    def test_equip_armor_cancels_effect(self):
        self.setupMageArmor()
        self.assertEqual(self.entity.armor_class(), 15)
        self.entity.equip('studded_leather', ignore_inventory=True)
        self.assertEqual(self.entity.armor_class(), 12)

    def test_chill_touch(self):
        random.seed(1002)
        self.assertEqual(self.npc.hp(), 9)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['chill_touch', 0])['next'](self.npc)
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['spell_damage', 'chill_touch'])
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 2)
        self.assertTrue(self.npc.has_spell_effect('chill_touch'))

        # target cannot heal until effect ends
        self.npc.heal(100)
        self.assertEqual(self.npc.hp(), 2)

        # drop effect until next turn
        self.entity.reset_turn(self.battle)
        self.npc.heal(100)
        self.assertNotEqual(self.npc.hp(), 3)

    def test_chill_touch_undead(self):
        random.seed(1003)
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[5, 5])
        self.assertEqual(self.npc.hp(), 13)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['chill_touch', 0])['next'](self.npc)
        action.resolve(self.session, self.battle_map, { "battle" : self.battle})
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 5)
        self.assertEqual(target_advantage_condition(self.battle, self.npc, self.entity, None), [-1, [[], ['chill_touch_disadvantage']]])

    def test_expeditious_retreat(self):
        action = SpellAction.build(self.session, self.entity)['next'](['expeditious_retreat', 0])
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['expeditious_retreat'])
        self.battle.commit(action)
        available_actions = [a.action_type for a in self.entity.available_actions(self.session, self.battle)]

        # can't cast another spell this turn
        self.assertNotIn('spell', available_actions)
        self.entity.reset_turn(self.battle)
        available_actions = [a.action_type for a in self.entity.available_actions(self.session, self.battle)]
        self.assertIn('spell', available_actions)
        self.assertIn('dash_bonus', available_actions)

    def test_magic_missile(self):
        random.seed(1003)
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        self.npc2 = self.session.npc('skeleton')
        self.battle.add(self.npc2, 'b', position=[2, 5])
        self.npc.reset_turn(self.battle)
        self.npc2.reset_turn(self.battle)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['magic_missile', 0])['next']([self.npc, self.npc2])
        valid_targets = self.battle.valid_targets_for(self.entity, action)
        print(valid_targets)
        self.assertEqual(len(valid_targets), 3)
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        starting_hp = [self.npc.hp(), self.npc2.hp()]
        self.assertEqual([s['type'] for s in action.result], ['spell_damage', 'spell_damage'])
        self.battle.commit(action)
        ending_hp = [self.npc.hp(), self.npc2.hp()]
        self.assertNotEqual(starting_hp, ending_hp)

    def test_ray_of_frost(self):
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        self.npc.reset_turn(self.battle)
        random.seed(1003)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['ray_of_frost', 0])['next'](self.npc)
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['spell_damage', 'ray_of_frost'])
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 7)
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

    def test_shield_spell(self):
        class CustomReactionController(Controller):
            def __init__(self, session):
                self.state = {}
                self.session = session
                self.battle_data = {}
                self.user = None

            def select_reaction(self, entity, battle, map, valid_actions, event):
                return valid_actions[0]
        self.battle.set_controller_for(self.entity, CustomReactionController(self.session))
        self.assertEqual(self.entity.armor_class(), 12)
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[1, 6])
        self.npc.reset_turn(self.battle)
        random.seed(1003)
        print(MapRenderer(self.battle_map).render())
        # make the skeleton attack the mage
        DieRoll.fudge(10)
        action = AttackAction(self.session, self.npc, 'attack')
        action.target = self.entity
        action.npc_action = {
            "name": "Short Sword",
            "type": 'melee_attack',
            "range": 5,
            "targets": 1,
            "attack": 4,
            "damage": 5,
            "damage_die": "1d6+2",
            "damage_type": "piercing"
        }
        self.battle.action(action)
        self.battle.commit(action)
        DieRoll.unfudge()
        self.assertEqual(self.entity.hp(), 0)

    def test_shield_spell_async(self):
        class CustomReactionController(Controller):
            def __init__(self, session):
                self.state = {}
                self.session = session
                self.battle_data = {}
                self.user = None

            def select_reaction(self, entity, battle, map, valid_actions, event):
                yield entity, event, valid_actions

        self.battle.set_controller_for(self.entity, CustomReactionController(self.session))
        self.assertEqual(self.entity.armor_class(), 12)
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[1, 6])
        self.npc.reset_turn(self.battle)
        random.seed(1003)
        print(MapRenderer(self.battle_map).render())
        # make the skeleton attack the mage
        DieRoll.fudge(10)
        action = AttackAction(self.session, self.npc, 'attack')
        action.target = self.entity
        action.npc_action = {
            "name": "Short Sword",
            "type": 'melee_attack',
            "range": 5,
            "targets": 1,
            "attack": 4,
            "damage": 5,
            "damage_die": "1d6+2",
            "damage_type": "piercing"
        }
        try:
            self.battle.action(action)
        except AsyncReactionHandler as e:
            print("waiting for reaction")
            if (e.reaction_type == 'shield'):
                for _, _, valid_actions in e.resolve():
                    e.send(valid_actions[0])
                action = self.battle.action(action)
        self.battle.commit(action)
        DieRoll.unfudge()
        self.assertEqual(self.entity.hp(), 0)

    def test_autobuild(self):
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        auto_build_actions = autobuild(self.session, SpellAction, self.entity, self.battle)
        self.assertEqual(len(auto_build_actions), 3)
        action_list = [str(a) for a in  auto_build_actions]
        
        self.assertEqual(action_list, ['SpellAction: firebolt to Skeleton',
                                       'SpellAction: mage_armor to Crysania',
                                       'SpellAction: magic_missile to (Skeleton, Skeleton, Skeleton)'])

        self.assertEqual(self.entity.armor_class(), 12)
        # must be a valid action
        for a in auto_build_actions:
            a.resolve(self.session, self.battle_map, { "battle": self.battle})
            self.battle.commit(a)
        # mage armor should take effect
        self.assertEqual(self.entity.armor_class(), 15)

    def test_find_familiar(self):
        # Cast find familiar spell
        print(MapRenderer(self.battle_map).render())
        action = autobuild(self.session, SpellAction, self.entity, None, map=self.battle_map, match=['find_familiar', 'bat', [0, 6]], verbose=True)[0]
        self.battle.action(action)
        self.battle.commit(action)
        entity = self.battle_map.entity_at(0, 6)
        self.assertEqual(entity.name, 'Bat')
        self.assertEqual(entity.owner, self.entity)
        print(MapRenderer(self.battle_map).render())

        self.assertEqual(len(self.entity.casted_effects), 1)
        # test dismiss

        for effect in self.entity.casted_effects:
            self.entity.remove_effect(effect['effect'], opts={'event': 'dismiss_familiar'})

        entity = self.battle_map.entity_at(0, 6)
        self.assertIsNone(entity)

        action = autobuild(self.session, SpellAction, self.entity, None, map=self.battle_map, match=['find_familiar', 'bat', [0, 6]], verbose=True)[0]
        self.battle.action(action)
        self.battle.commit(action)

        # test send to pocket dimension
        action = autobuild(self.session, FindFamiliarAction, self.entity, None, map=self.battle_map, match=['dismiss_temporary'], verbose=True)[0]

        self.battle.action(action)
        self.battle.commit(action)
        entity = self.battle_map.entity_at(0, 6)
        self.assertIsNone(entity)

        self.assertEqual(len(self.entity.pocket_dimension), 1)

        # resummon
        action = autobuild(self.session, SummonFamiliarAction, self.entity, self.battle, map=self.battle_map, match=[[3, 5]], verbose=True)[0]
        self.battle.action(action)
        self.battle.commit(action)
        entity = self.battle_map.entity_at(3, 5)
        self.assertIsNotNone(entity)
        self.assertEqual(entity.name, 'Bat')
        self.assertEqual(entity.owner, self.entity)


    def test_protection_from_poison(self):
        random.seed(1003)
        print(MapRenderer(self.battle_map).render())

        action = SpellAction.build(self.session, self.entity)['next'](['protection_from_poison', 0])['next'](self.entity)
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.battle.commit(action)
        self.assertEqual(self.entity.effective_resistances(), ['poison'])
        
if __name__ == '__main__':
    unittest.main()
