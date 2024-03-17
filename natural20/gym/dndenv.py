import gymnasium as gym
from typing import Any, Dict, List, Tuple, Union
from natural20.map import Map, Terrain
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.map_renderer import MapRenderer
from natural20.die_roll import DieRoll
from natural20.generic_controller import GenericController
from natural20.utils.utils import Session
from natural20.actions.move_action import MoveAction
from natural20.action import Action
from natural20.gym.types import EnvObject, Environment
import random

"""
This is a custom environment for the game Dungeons and Dragons 5e. It is based on the OpenAI Gym environment.
"""
class dndenv(gym.Env):
    def __init__(self, session, map, battle, render_mode = None):
        self.session = session
        self.map = map
        self.battle = battle
        self.render_mode = render_mode
       
        self.observation_space = gym.spaces.Dict(spaces={
            "map": gym.spaces.Box(low=-1, high=256, shape=self.map.size, dtype=int),
            "objects": gym.spaces.Sequence(gym.spaces.Dict(spaces={
                "name": gym.spaces.Box(low=0, high=256, shape=(1,), dtype=int),
                "type": gym.spaces.Box(low=0, high=256, shape=(1,), dtype=int),
                "health": gym.spaces.Box(low=0, high=1, shape=(1,), dtype=float),
                "location": gym.spaces.Box(low=0, high=256, shape=(2,), dtype=int),
                "weapons": gym.spaces.Box(low=0, high=256, shape=(1,), dtype=int),
                "is_enemy": gym.spaces.Box(low=0, high=1, shape=(1,), dtype=bool)
            }))
        })
        self.action_space = gym.spaces.Sequence(gym.spaces.Dict(spaces={
            "action": gym.spaces.Discrete(256),
            "target": gym.spaces.Discrete(256),
            "as_reaction": gym.spaces.Discrete(2)
        }))
        self.reward_range = (-1, 1)
        self.metadata = {}
        self.spec = None
        self._seed = None

    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None) -> tuple[Environment, dict[str, Any]]
        super().reset(seed=seed)
        self.session = Session('templates')
        self.map = Map('templates/maps/game_map.yml')
        self.battle = Battle(self.session, map)
        return self._observe()
    
    def _observe(self) -> tuple[Environment, dict[str, Any]]:
        map_renderer = MapRenderer(self.map)
        observed_map = map_renderer.render(self.map)
        environment = Environment(self.map, [], {})
        return environment, {}

    def step(self, action):
        pass