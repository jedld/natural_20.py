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
        self.assertEqual(self.npc.hp(), 6)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)['next'](['sacred_flame',0])['next'](self.npc)
        action.resolve(self.session, self.battle_map, { "battle": self.battle})
        self.assertEqual([s['type'] for s in action.result], ['spell_damage'])
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 0)


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
        self.assertEqual(len(auto_build_actions), 1)
        self.assertEqual([str(a) for a in  auto_build_actions], ['SpellAction: sacred_flame'])

if __name__ == '__main__':
    unittest.main()
