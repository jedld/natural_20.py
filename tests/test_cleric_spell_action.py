import unittest
from natural20.actions.spell_action import SpellAction
from natural20.actions.attack_action import AttackAction
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

class TestClericSpellAction(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=event_manager)
    
    def setUp(self):
        random.seed(7000)
        self.session = self.make_session()
        self.entity = PlayerCharacter.load(self.session, 'dwarf_cleric.yml')
        self.battle_map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.battle_map)
        self.npc = self.battle_map.entity_at(5, 5)
        self.battle.add(self.entity, 'a', position=[0, 5])
        self.entity.reset_turn(self.battle)

    def test_sacred_flame(self):
        random.seed(7003)
        self.assertEqual(self.npc.hp(), 9)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['sacred_flame',0])['next'](self.npc)
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['spell_damage'])
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 1)

    def test_guiding_bolt(self):
        random.seed(7009)
        self.npc.attributes['hp'] = 21
        self.assertEqual(self.npc.hp(), 21)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['guiding_bolt',0])['next'](self.npc)
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['spell_damage', 'guiding_bolt'])
        self.battle.commit(action)

        adv_mod, adv_info = target_advantage_condition(self.battle, self.entity, self.npc, action.spell_action.properties)
        self.assertEqual(adv_info, [['guiding_bolt_advantage'], []])
        self.assertEqual(adv_mod, 1)
        self.assertEqual(self.npc.hp(), 1)
        self.entity.resolve_trigger('end_of_turn')
        adv_mod, adv_info = target_advantage_condition(self.battle, self.entity, self.npc, action.spell_action.properties)
        self.assertEqual(adv_mod, 1)
        self.assertEqual(adv_info, [['guiding_bolt_advantage'], []])
        self.entity.resolve_trigger('start_of_turn')
        self.entity.resolve_trigger('end_of_turn')
        adv_mod, adv_info = target_advantage_condition(self.battle, self.entity, self.npc, action.spell_action.properties)
        self.assertEqual(adv_mod, 0)
        self.assertEqual(adv_info, [[], []])


    def test_cure_wounds(self):
        random.seed(7003)
        self.entity.take_damage(4)
        self.assertEqual(self.entity.hp(), 4)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['cure_wounds',0])['next'](self.entity)
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['spell_heal'])
        self.battle.commit(action)
        self.assertEqual(self.entity.hp(), 8)

    def test_bless(self):
        random.seed(7003)
        self.entity2 = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(self.entity2, 'a', position=[0, 6], token='E')
        self.entity2.reset_turn(self.battle)
        bless_action = SpellAction.build(self.session, self.entity)['next'](['bless', 0])['next']([self.entity2])
        bless_action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in bless_action.result], ['bless'])
        self.battle.commit(bless_action)

        self.assertEqual(str(self.entity.current_concentration()), "bless")
        self.assertTrue(self.entity2.has_effect('bless'))
        print(MapRenderer(self.battle_map).render())

        action = AttackAction.build(self.session,  self.entity2)['next'](self.npc)['next']('dagger')['next']()
        action = action.resolve(self.session, self.battle_map, { "battle": self.battle})
        result = action.result[0]
        self.assertEqual(str(result['attack_roll']), "d20(4) + 8 + d4(4)")
        result = self.entity2.save_throw('wisdom', self.battle)
        self.assertEqual(str(result),"d20(9) + 1 + d4(4)")
        self.entity2.dismiss_effect(bless_action.spell_action)
        result = self.entity2.save_throw('wisdom', self.battle)
        self.assertEqual(str(result),"d20(10) + 1")

    def test_compute_hit_probability(self):
        self.entity.ability_scores['wis'] = 20
        self.npc = self.session.npc('ogre')
        self.battle.add(self.npc, 'b', position=[0, 6])

        self.npc.reset_turn(self.battle)
        self.assertEqual(self.entity.spell_save_dc("wisdom"), 15)

        action = SpellAction.build(self.session, self.entity)['next'](['sacred_flame', 0])['next'](self.npc)
        self.assertAlmostEqual(action.compute_hit_probability(self.battle), 0.75)
        self.assertAlmostEqual(action.avg_damage(self.battle), 4.5)

    def test_autobuild(self):
        self.npc = self.session.npc('skeleton')
        self.battle.add(self.npc, 'b', position=[0, 6])
        auto_build_actions = autobuild(self.session, SpellAction, self.entity, self.battle)
        self.assertEqual(len(auto_build_actions), 3)
        self.assertEqual([str(a) for a in  auto_build_actions], ['SpellAction: sacred_flame', 'SpellAction: cure_wounds', 'SpellAction: guiding_bolt'])

if __name__ == '__main__':
    unittest.main()
