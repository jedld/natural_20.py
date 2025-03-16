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
from natural20.web.json_renderer import JsonRenderer
from natural20.map_renderer import MapRenderer

from natural20.utils.serialization import Serialization
import uuid
import yaml
import os

class TestSerialization(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        random.seed(7000)
        return Session(root_path='tests/fixtures', event_manager=event_manager)

    def test_savegame(self):
        session = self.make_session()
        battle_map = Map(session, 'entryway')
        battle = Battle(session, battle_map)
        character = battle_map.entity_by_uid('gomerin')
        battle.add(character, 'a', token='G')
        character.reset_turn(battle)


        # action = autobuild(session, AttackAction, character, battle, match=[npc, 'vicious_rapier'])[0]
        temp_directory = 'tests/fixtures/tmp'
        os.makedirs(temp_directory, exist_ok=True)
        random_filename = os.path.join(temp_directory, uuid.uuid4().hex)
        serializer = Serialization()
        yaml = serializer.serialize(session, battle, [battle_map], filename=random_filename)
        new_session, new_battle, new_maps = serializer.deserialize(yaml)
        print(MapRenderer(battle_map, battle).render())
        print(MapRenderer(new_maps[0], new_battle).render())

        json_render = JsonRenderer(new_maps[0], new_battle).render()
        json_render_2 = JsonRenderer(battle_map, battle).render()
        self.assertEqual(json_render, json_render_2)
        os.remove(random_filename)