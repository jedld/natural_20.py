import unittest
from natural20.map import Map, Terrain
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.map_renderer import MapRenderer
from natural20.die_roll import DieRoll
from natural20.generic_controller import GenericController
from natural20.utils.utils import Session
from natural20.actions.move_action import MoveAction
from natural20.action import Action
from natural20.gym.dndenv import dndenv
from gymnasium import register, envs, make
import random


class TestGym(unittest.TestCase):
    def setUp(self):
        session = Session('templates')
        map = Map('templates/maps/game_map.yml')
        battle = Battle(session, map)
        fighter = PlayerCharacter(session, 'templates/characters/high_elf_fighter.yml', name="Gomerin")
        rogue = PlayerCharacter(session, 'templates/characters/halfling_rogue.yml', name="Rogin")

        # add fighter to the battle at position (0, 0) with token 'G' and group 'a'
        battle.add(fighter, 'a', position=[0, 0], token='G', add_to_initiative=True, controller=None)
        battle.add(rogue, 'b', position=[5, 5], token='R', add_to_initiative=True, controller=None)
        battle.start()
        
        self.env = dndenv(session, map, battle)
        register(id='dndenv-v0', entry_point=lambda **kwargs: self.env)

    def test_reset(self):
        env = make("dndenv-v0", render_mode="human")
        observation, info = env.reset(seed=42)
        assert env is not None

