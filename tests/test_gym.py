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
        self.env = dndenv()
        register(id='dndenv-v0', entry_point=lambda **kwargs: self.env)

    def test_reset(self):
        env = make("dndenv-v0", render_mode="human")
        observation, info = env.reset(seed=42)
        print(observation)
        print(info)
        assert env is not None
        assert info is not None

