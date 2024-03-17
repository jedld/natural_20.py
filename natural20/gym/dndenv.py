import gymnasium as gym
from natural20.map import Map, Terrain
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.map_renderer import MapRenderer
from natural20.die_roll import DieRoll
from natural20.generic_controller import GenericController
from natural20.utils.utils import Session
from natural20.actions.move_action import MoveAction
from natural20.action import Action
import random

class dndenv(gym.Env):
    def __init__(self, render_mode = None):
        self.render_mode = render_mode
        self.observation_space = gym.spaces.Discrete(1)
        self.action_space = gym.spaces.Discrete(1)
        self.reward_range = (-1, 1)
        self.metadata = {}
        self.spec = None
        self._seed = None

        self.session = Session('templates')
        self.map = Map('templates/maps/game_map.yml')
        self.battle = Battle(self.session, map)

    def step(self, action):
        pass