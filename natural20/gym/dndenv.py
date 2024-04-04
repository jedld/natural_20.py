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
    def __init__(self, view_port_size=(10, 10), max_rounds=10, render_mode = None):
        self.render_mode = render_mode
        self.view_port_size = view_port_size
        self.max_rounds = max_rounds
        self.metadata = {
            'render.modes': ['ansi']
        }
        self.observation_space = gym.spaces.Box(low=-1, high=255, shape=(view_port_size[0], view_port_size[0], 4), dtype=int)
        self.action_space = gym.spaces.Sequence(gym.spaces.Dict(spaces={
            "action": gym.spaces.Discrete(256),
            "direction": gym.spaces.Discrete(8),
            "target": gym.spaces.Discrete(256),
            "as_reaction": gym.spaces.Discrete(2)
        }))

        self.session = Session('templates')
        self.map = Map('templates/maps/game_map.yml')
        self.battle = Battle(self.session, self.map)
        self.players = []

        self.players.append(('a', 'G', PlayerCharacter(self.session, 'templates/characters/high_elf_fighter.yml', name="Gomerin"), [2, 0]))
        self.players.append(('b', 'R', PlayerCharacter(self.session, 'templates/characters/halfling_rogue.yml', name="Rogin"), [2,4]))

        # add fighter to the battle at position (0, 0) with token 'G' and group 'a'
        for group, token, player, position in self.players:
            self.battle.add(player, group, position=position, token=token, add_to_initiative=True, controller=None)

        self.battle.start()

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
    
    def _render_terrain_ansi(self):
        result = []
        current_player = self.battle.current_turn()
        pos_x, pos_y = self.map.position_of(current_player)
        view_w, view_h = self.view_port_size
        map_w, map_h = self.map.size
        for x in range(-view_w//2, view_w//2):
            col_arr = []
            for y in range(-view_h//2, view_h//2):
                if pos_x + x < 0 or pos_x + x >= map_w or pos_y + y < 0 or pos_y + y >= map_h:
                    col_arr.append("*")
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

                    col_arr.append(f"{entity_int}")
            
            result.append(col_arr)
        return np.array(result)

    def render(self, mode='ansi'):
        if mode == 'ansi':
            return self._render_terrain_ansi()
        else:
            return None

    def reset(self, **kwargs) -> Dict[str, Any]:
        self.battle.start_turn()
        if self.battle.current_turn().conscious():
                self.battle.current_turn().reset_turn(self.battle)
                
        return self._render_terrain(), { "available_moves": self._compute_available_moves(self.battle.current_turn(), self.battle), "current_index" : self.battle.current_turn_index }

    def step(self, action):
        entity = self.battle.current_turn()
        action_type, param1, param2, param3 = action
        available_actions = entity.available_actions(self.session, self.battle)
        for action in available_actions:
            if action.action_type == "attack" and action_type == 0:
                action.target = self.map.entity_at(param1, param2)
                self.battle.action(action)
                self.battle.commit(action)
                break
            elif action.action_type == "move" and action_type == 1:
                action.move_path = [(self.map.position_of(entity)[0], self.map.position_of(entity)[1]), (param1, param2)]
                self.battle.action(action)
                self.battle.commit(action)
                break
            elif action.action_type == "disengage" and action_type == 2:
                self.battle.action(action)
                self.battle.commit(action)
                break
            elif action.action_type == "dodge" and action_type == 3:
                self.battle.action(action)
                self.battle.commit(action)
                break
            elif action.action_type == "dash" and action_type == 4:
                self.battle.action(action)
                self.battle.commit(action)
                break
            elif action.action_type == "dash_bonus" and action_type == 5:
                self.battle.action(action)
                self.battle.commit(action)
                break
            elif action.action_type == "stand" and action_type == 6:
                self.battle.action(action)
                self.battle.commit(action)
                break
        available_actions = entity.available_actions(self.session, self.battle)
        
        reward = 0
        done = False
        if len(available_actions) == 0:
            self.battle.end_turn()
            self.battle.start_turn()
            if self.battle.current_turn().conscious():
                self.battle.current_turn().reset_turn(self.battle)
            result = self.battle.next_turn(max_rounds=self.max_rounds)
            print(f"Result: {result}")
            if result == 'tpk':
                reward = 1
        return self._render_terrain(), reward, done, { "available_moves": self._compute_available_moves(self.battle.current_turn(), self.battle), "current_index" : self.battle.current_turn_index }      

    def _action_type_to_int(self, action_type):
        if action_type == "attack":
            return 0
        elif action_type == "move":
            return 1
        elif action_type == "disengage":
            return 2
        elif action_type == "dodge":
            return 3
        elif action_type == "dash":
            return 4
        elif action_type == "dash_bonus":
            return 5
        elif action_type == "stand":
            return 6
        else:
            return -1

    def _compute_available_moves(self, entity: Entity, battle):
        available_actions = entity.available_actions(self.session, battle)

        # generate available targets
        valid_actions = []       

        # try to stand if prone
        if entity.prone() and StandAction.can(entity, battle):
            valid_actions.append((6, -1, -1, -1))
        
        entity_pos = self.map.position_of(entity)

        for action in available_actions:
            if action.action_type == "attack":
                valid_targets = battle.valid_targets_for(entity, action)
                if valid_targets:
                    action.target = valid_targets[0]
                    targets = self.map.entity_squares(valid_targets[0])
                    
                    for target in targets:
                        relative_pos = (target[0] - entity_pos[0], target[1] - entity_pos[1])
                        if relative_pos[0] >=0 and relative_pos[0] < self.view_port_size[0] and relative_pos[1] >= 0 and relative_pos[1] < self.view_port_size[1]:
                            valid_actions.append((0, relative_pos[0], relative_pos[1], -1))
            elif action.action_type == "move":
                relative_x = action.move_path[1][0] - entity_pos[0]
                relative_y = action.move_path[1][1] - entity_pos[1]
                valid_actions.append((1,relative_x, relative_y, 0))
            elif action.action_type == "disengage":
                valid_actions.append((2, -1, -1, -1))
            elif action.action_type == 'dodge':
                valid_actions.append((3, -1, -1, -1))
            elif action.action_type == 'dash':
                valid_actions.append((4, -1, -1, -1))
            elif action.action_type == 'dash_bonus':
                valid_actions.append((5, -1, -1, -1))

        return valid_actions
