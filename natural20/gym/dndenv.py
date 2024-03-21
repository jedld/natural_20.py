import gymnasium as gym
import numpy as np
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
    def __init__(self, session: Session, map: Map, battle: Battle, view_port_size=(10, 10), render_mode = None):
        self.session = session
        self.map = map
        self.battle = battle
        self.render_mode = render_mode
        self.view_port_size = view_port_size
       
        self.observation_space = gym.spaces.Dict(spaces={
            "terrain": gym.spaces.Box(low=-1, high=256, shape=view_port_size, dtype=int),
            "entities": gym.spaces.Box(low=-1, high=256, shape=view_port_size, dtype=int),
            "current_turn": gym.spaces.Discrete(256),
            "current_hp": gym.spaces.Box(low=0, high=256, shape=(1,), dtype=int),
            # "objects": gym.spaces.Sequence(gym.spaces.Dict(spaces={
            #     "name": gym.spaces.Box(low=0, high=256, shape=(1,), dtype=int),
            #     "type": gym.spaces.Box(low=0, high=256, shape=(1,), dtype=int),
            #     "hp": gym.spaces.Box(low=0, high=1, shape=(1,), dtype=float),
            #     "location": gym.spaces.Box(low=0, high=256, shape=(2,), dtype=int),
            #     "weapons": gym.spaces.Box(low=0, high=256, shape=(1,), dtype=int),
            #     "is_enemy": gym.spaces.Box(low=0, high=1, shape=(1,), dtype=bool)
            # }
            # ))
        })

        self.action_space = gym.spaces.Sequence(gym.spaces.Dict(spaces={
            "action": gym.spaces.Discrete(256),
            "direction": gym.spaces.Discrete(8),
            "target": gym.spaces.Discrete(256),
            "as_reaction": gym.spaces.Discrete(2)
        }))

        self.reward_range = (-1, 1)
        self.metadata = {}
        self.spec = None
        self._seed = None

    def _render_terrain(self):
        result = []
        current_player = self.battle.current_turn()
        pos_x, pos_y = self.map.position_of(current_player)
        view_w, view_h = self.view_port_size
        map_w, map_h = self.map.size
        for x in range(-view_w//2, view_w//2):
            col_arr = []
            for y in range(-view_h//2, view_h//2):
                if pos_x + x < 0 or pos_x + x >= map_w or pos_y + y < 0 or pos_y + y >= map_h:
                    col_arr.append(-1)
                else:
                    col_arr.append(0)
            
            result.append(col_arr)
        return result
    
    def _render_entities(self):
        result = []
        current_player = self.battle.current_turn()
        pos_x, pos_y = self.map.position_of(current_player)
        view_w, view_h = self.view_port_size
        map_w, map_h = self.map.size
        for x in range(-view_w//2, view_w//2):
            col_arr = []
            for y in range(-view_h//2, view_h//2):
                if pos_x + x < 0 or pos_x + x >= map_w or pos_y + y < 0 or pos_y + y >= map_h:
                    col_arr.append(-1)
                elif x == 0 and y == 0:
                    col_arr.append(1)
                elif self.map.entity_at(pos_x + x, pos_y + y) is not None:
                    col_arr.append(2)
                else:
                    col_arr.append(0)
            
            result.append(col_arr)
        return result
    
    def reset(self, **kwargs) -> Dict[str, Any]:
        observation = {}
        observation["current_hp"] = np.array([self.battle.current_turn().hp()])
        observation["current_turn"] = np.int64(self.battle.current_turn_index)
        observation["entities"] = np.array(self._render_entities())
        observation["terrain"] = np.array(self._render_terrain())
        
        return observation, {}

    def step(self, action):
        pass