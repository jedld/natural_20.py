import unittest
import random
from natural20.session import Session
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.actions.attack_action import AttackAction, TwoWeaponAttackAction
from natural20.map_renderer import MapRenderer
from natural20.utils.ac_utils import calculate_cover_ac
from natural20.weapons import compute_advantages_and_disadvantages
from natural20.utils.action_builder import autobuild
import pdb


class TestAttackAction(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        random.seed(7000)
        return Session(root_path='tests/fixtures', event_manager=event_manager)

    def test_attack_action(self):
        session = self.make_session()
        battle_map = Map(session, 'battle_sim')
        battle = Battle(session, battle_map)
        character = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        npc = session.npc('ogre')
        npc2 = session.npc('goblin')

        battle.add(character, 'a', position='spawn_point_1', token='G')
        battle.add(npc, 'b', position='spawn_point_2', token='g')

        character.reset_turn(battle)
        npc.reset_turn(battle)

        battle_map.move_to(character, 0, 0, battle)
        battle_map.move_to(npc, 1, 0, battle)
        battle.add(character, 'a', token='G')
        battle.add(npc, 'b', token='g')

        character.reset_turn(battle)
        npc.reset_turn(battle)

        ptr = autobuild(session, AttackAction, character, battle, match=[npc, 'vicious_rapier'])[0]

        self.assertEqual(ptr.target, npc)
        self.assertEqual(ptr.source, character)
        self.assertEqual(ptr.using, 'vicious_rapier')

    def test_two_weapon_fighting(self):
        session = self.make_session()
        battle_map = Map(session, 'battle_sim')
        battle = Battle(session, battle_map)
        character = PlayerCharacter.load(session, 'elf_rogue.yml', { "equipped" : ['dagger', 'dagger'] })

        npc = session.npc('goblin')

        battle.add(character, 'a', position='spawn_point_1', token='G')
        battle.add(npc, 'b', position='spawn_point_2', token='g')
        battle.start()
        battle_map.move_to(character, 0, 0, battle)
        battle_map.move_to(npc, 1, 0, battle)

        character.reset_turn(battle)
        npc.reset_turn(battle)

        map_renderer = MapRenderer(battle_map)
        map_renderer.render(battle)

        self.assertFalse(TwoWeaponAttackAction.can(character, battle))

        action =  autobuild(session, AttackAction, character, battle, match=[npc,'dagger'])[0]
        action.resolve(session, battle_map, { "battle": battle})
        battle.commit(action)
        self.assertTrue(TwoWeaponAttackAction.can(character, battle))
        battle.set_current_turn(character)
        available_act = character.available_actions(session, battle)
        available_act = [act.action_type for act in available_act]
        self.assertTrue('two_weapon_attack' in available_act)

    def test_two_weapon_fighting_not_available(self):
        session = self.make_session()
        battle_map = Map(session, 'battle_sim')
        battle = Battle(session, battle_map)
        character = PlayerCharacter.load(session, 'elf_rogue.yml', { "equipped" : ['dagger'] })

        npc = session.npc('goblin')

        battle.add(character, 'a', position='spawn_point_1', token='G')
        battle.add(npc, 'b', position='spawn_point_2', token='g')

        battle_map.move_to(character, 0, 0, battle)
        battle_map.move_to(npc, 1, 0, battle)

        character.reset_turn(battle)
        npc.reset_turn(battle)

        map_renderer = MapRenderer(battle_map)
        map_renderer.render(battle)
        action =  autobuild(session, AttackAction, character, battle, match=[npc, 'dagger'])[0]
        action.resolve(session, battle_map, { "battle": battle})
        battle.commit(action)

        available_act = character.available_actions(session, battle)
        available_act = [act.action_type for act in available_act]
        self.assertFalse('two_weapon_attack' in available_act)

    def test_calculate_cover_ac(self):
        session = self.make_session()
        battle_map = Map(session, 'battle_sim_objects')
        character = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        npc2 = session.npc('goblin')

        battle_map.place((1, 2), character, 'G')
        battle_map.place((5, 2), npc2, 'g')

        map_renderer = MapRenderer(battle_map)
        print(map_renderer.render())

        self.assertEqual(calculate_cover_ac(battle_map, character, npc2), 0)
        self.assertEqual(calculate_cover_ac(battle_map, npc2, character), 2)

    def test_compute_hit_probability(self):
        session = self.make_session()
        battle_map = Map(session, 'battle_sim')
        battle = Battle(session, battle_map)
        character = PlayerCharacter.load(session, 'high_elf_fighter')
        npc = session.npc('ogre')

        battle.add(character, 'a', position="spawn_point_1", token='G')
        battle.add(npc, 'b', position="spawn_point_2", token='g')
        character.reset_turn(battle)
        battle.start()
        battle.set_current_turn(character)
        battle_map.move_to(character, 0, 5, battle)

        map_renderer = MapRenderer(battle_map)
        print(map_renderer.render())

        action = AttackAction.build(session, character)['next']('unarmed_attack')['next'](npc)
        hit_probability = action.compute_hit_probability(battle)
        self.assertAlmostEqual(hit_probability, 0.70, places=2)

    def test_pack_tactics(self):
        session = self.make_session()
        battle_map = Map(session, 'battle_sim')
        battle = Battle(session, battle_map)
        character = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        battle.add(character, 'a', position='spawn_point_1', token='G')
        npc = session.npc('wolf')
        npc2 = session.npc('wolf')

        battle_map.move_to(character, 0, 5, battle)
        battle.add(npc, 'b', position=[1, 5])
        battle.add(npc2, 'b', position=[0, 6])

        map_renderer = MapRenderer(battle_map)
        print(map_renderer.render())

        advantages, disadvantages = compute_advantages_and_disadvantages(session, npc, character, npc.npc_actions[0], battle=battle)
        self.assertEqual(advantages, ['pack_tactics'])
        self.assertEqual(disadvantages, [])

    def test_no_pack_tactics_if_no_ally(self):
        session = self.make_session()
        battle_map = Map(session, 'battle_sim')
        battle = Battle(session, battle_map)
        character = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        battle.add(character, 'a', position='spawn_point_1', token='G')
        npc = session.npc('wolf')
        npc2 = session.npc('wolf')
        battle.add(npc, 'b', position=[1, 5])
        battle.add(npc2, 'b', position=[0, 6])
        battle_map.move_to(character, 0, 5, battle)
        battle_map.move_to(npc2, 2, 5, battle)

        map_renderer = MapRenderer(battle_map)
        print(map_renderer.render())

        advantages, disadvantages = compute_advantages_and_disadvantages(session, npc, character, npc.npc_actions[0], battle=battle)
        self.assertEqual(advantages, [])
        self.assertEqual(disadvantages, [])

if __name__ == '__main__':
    unittest.main()
