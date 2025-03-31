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
from natural20.die_roll import DieRoll
from pdb import set_trace
from natural20.utils.action_builder import autobuild
import pdb

class TestEffects(unittest.TestCase):
    def make_session(self):
            event_manager = EventManager()
            event_manager.standard_cli()
            random.seed(7000)
            return Session(root_path='tests/fixtures', event_manager=event_manager)
    
    def test_attack_with_resistances(self):
        session = self.make_session()
        battle_map = Map(session, 'battle_sim')
        battle = Battle(session, battle_map)
        character = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        npc = session.npc('specter')

        battle.add(character, 'a', position='spawn_point_1', token='G')
        battle.add(npc, 'b', position='spawn_point_2', token='g')

        character.reset_turn(battle)
        npc.reset_turn(battle)

        battle_map.move_to(character, 0, 0, battle)
        battle_map.move_to(npc, 1, 0, battle)
        battle.add(character, 'a', token='G')
        battle.add(npc, 'b', token='g')
        battle.start()
        character.reset_turn(battle)
        npc.reset_turn(battle)
        battle.set_current_turn(character)
        self.assertEqual(npc.resistant_to('piercing'), True)
        print(MapRenderer(battle_map).render())
        actions = autobuild(session, AttackAction, character, battle, battle_map)
        self.assertEqual([str(a) for a in actions], ['Gomerin uses vicious_rapier on Specter', 'Gomerin uses longbow on Specter'])
        random.seed(7000)
        self.assertEqual(npc.hp(), 22)
        battle.action(actions[0])
        battle.commit(actions[0])
        self.assertEqual(actions[0].result[0]['damage'], 6)
        self.assertEqual(npc.hp(), 19)

    def test_life_drain(self):
        session = self.make_session()
        battle_map = Map(session, 'battle_sim')
        battle = Battle(session, battle_map)
        character = PlayerCharacter.load(session, 'high_elf_mage.yml')
        npc = session.npc('specter')

        battle.add(character, 'a', position='spawn_point_1', token='G')
        battle.add(npc, 'b', position='spawn_point_2', token='g')
        character.properties['max_hp'] = 100
        character.attributes['hp'] = 100
        character.reset_turn(battle)
        npc.reset_turn(battle)

        battle_map.move_to(character, 0, 0, battle)
        battle_map.move_to(npc, 1, 0, battle)
        battle.add(character, 'a', token='G')
        battle.add(npc, 'b', token='g')
        battle.start()
        character.reset_turn(battle)
        npc.reset_turn(battle)
        battle.set_current_turn(npc)
        self.assertEqual(npc.resistant_to('piercing'), True)
        print(MapRenderer(battle_map).render())
        actions = autobuild(session, AttackAction, npc, battle, battle_map)
        self.assertEqual([str(a) for a in actions], ['Specter uses Life Drain on Crysania'])
        random.seed(1115)
        battle.action(actions[0])
        battle.commit(actions[0])
        self.assertEqual(character.hp(), 95)
        self.assertEqual(character.max_hp(), 95)
        character.long_rest()
        self.assertEqual(character.max_hp(), 100)

    def test_strength_drain(self):
        session = self.make_session()
        battle_map = Map(session, 'battle_sim')
        battle = Battle(session, battle_map)
        character = PlayerCharacter.load(session, 'high_elf_mage.yml')
        npc = session.npc('shadow')

        battle.add(character, 'a', position='spawn_point_1', token='G')
        battle.add(npc, 'b', position='spawn_point_2', token='g')
        character.properties['max_hp'] = 100
        character.attributes['hp'] = 100
        character.reset_turn(battle)
        npc.reset_turn(battle)

        battle_map.move_to(character, 0, 0, battle)
        battle_map.move_to(npc, 1, 0, battle)
        battle.add(character, 'a', token='G')
        battle.add(npc, 'b', token='g')
        battle.start()
        character.reset_turn(battle)
        npc.reset_turn(battle)
        battle.set_current_turn(npc)
        self.assertEqual(npc.resistant_to('piercing'), True)
        print(MapRenderer(battle_map).render())
        actions = autobuild(session, AttackAction, npc, battle, battle_map)
        self.assertEqual([str(a) for a in actions], ['Shadow uses Strength Drain on Crysania'])
        random.seed(1115)
        self.assertEqual(character.strength(), 10)
        battle.action(actions[0])
        battle.commit(actions[0])
        self.assertEqual(character.strength(), 9)
        npc.reset_turn(battle)
        actions = autobuild(session, AttackAction, npc, battle, battle_map)

        DieRoll.fudge(20)
        # test stackability
        battle.action(actions[0])
        battle.commit(actions[0])
        self.assertEqual(character.strength(), 7)

        character.long_rest()
        self.assertEqual(character.strength(), 10)