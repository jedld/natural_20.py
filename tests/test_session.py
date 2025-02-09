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
from pdb import set_trace
from natural20.utils.action_builder import autobuild
import uuid
import yaml

class TestSession(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        random.seed(7000)
        return Session(root_path='tests/fixtures', event_manager=event_manager)

    def test_savegame(self):
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

        # action = autobuild(session, AttackAction, character, battle, match=[npc, 'vicious_rapier'])[0]
        
        random_filename = uuid.uuid4().hex


        with open(f'{random_filename}.yml', 'w') as f:
            f.write(yaml.safe_dump(battle_map.to_dict()))

        battle_map_load = Map.from_dict(session, yaml.safe_load(open(f'{random_filename}.yml', 'r')))
        self.assertEqual(battle_map.to_dict(), battle_map_load.to_dict())
