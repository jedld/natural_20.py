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
import numpy as np

class TestGym(unittest.TestCase):
    def test_reset(self):
        env = make("dndenv-v0", render_mode="ansi", root_path='tests/fixtures', debug=True)
        observation, info = env.reset(seed=42)
        # sample a move from info
        while True:
            action = random.choice(info["available_moves"])
            observation, reward, done, truncated, info = env.step(action)
            assert observation is not None
            assert reward is not None
            if done or truncated:
                break
        assert env is not None
        assert info is not None

    def test_ability_info(self):
        env = make("dndenv-v0", render_mode="ansi", root_path='tests/fixtures', debug=True)
        observation, info = env.reset(seed=42)
        assert observation['ability_info'][0] == 1, observation['ability_info']
        _, _, main_player, _ = env.players[0]
        main_player.second_wind_count = 0
        observation = env.generate_observation(main_player)
        assert observation['ability_info'][0] == 0

    def test_render(self):
        env = make("dndenv-v0", render_mode="ansi", root_path='tests/fixtures', debug=True)
        observation, info = env.reset(seed=42)
        assert observation is not None
        assert info is not None

        
        # sample a move from info
        render = env.render()
        expected = """____________
____________
____________
____________
____________
____________
_.....P_____
_......_____
_......_____
_..##.._____
_.   .._____
_   ..._____"""
        assert render==expected, f"render: {render}"

