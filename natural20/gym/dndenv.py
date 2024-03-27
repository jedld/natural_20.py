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
from natural20.entity import Entity
from natural20.actions.look_action import LookAction
from natural20.actions.stand_action import StandAction
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
       
        self.observation_space = gym.spaces.Box(low=-1, high=255, shape=(view_port_size[0], view_port_size[0], 4), dtype=int)
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
                    col_arr.append([-1, 0, 0, 0])
                else:
                    terrain = self.map.base_map[pos_x + x][pos_y + y]

                    if terrain == None:
                        terrain_int = 0
                    else:
                        terrain_int = 1

                    entity = self.map.entity_at(pos_x + x, pos_y + y)

                    if entity == None:
                        entity_int = 0
                    elif entity == current_player:
                        entity_int = 1
                    elif self.battle.opposing(current_player, entity):
                        entity_int = 2
                    else:
                        entity_int = 3

                    col_arr.append([entity_int, terrain_int, 0, 0])
            
            result.append(col_arr)
        return np.array(result)
    
    def reset(self, **kwargs) -> Dict[str, Any]:
        return self._render_terrain(), {}

    def step(self, action):
        pass

    def _compute_available_moves(self, entity: Entity, battle):
        self._initialize_battle_data(battle, entity)

        enemy_positions = {}
        available_actions = entity.available_actions(self.session, battle)

        # generate available targets
        valid_actions = []
        # check if enemy positions is empty
        

        if len(enemy_positions.keys()) == 0 and LookAction.can(entity, battle):
            action = LookAction(self.session, entity, "look")
            valid_actions.append(action)

        # try to stand if prone
        if entity.prone() and StandAction.can(entity, battle):
            valid_actions.append(StandAction(None, entity, "stand"))

        for action in available_actions:
            if action.action_type == "attack":
                valid_targets = battle.valid_targets_for(entity, action)
                if valid_targets:
                    action.target = valid_targets[0]
                    valid_actions.append(action)
            elif action.action_type == "move":
                valid_actions.append(action)
            elif action.action_type == "disengage":
                valid_actions.append(action)
            elif action.action_type == 'dodge':
                valid_actions.append(action)
            elif action.action_type == 'dash':
                valid_actions.append(action)
            elif action.action_type == 'dash_bonus':
                valid_actions.append(action)

        return valid_actions
