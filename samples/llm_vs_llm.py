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
from natural20.gym.dndenv import dndenv, action_type_to_int
from gymnasium import register, envs, make
from llm_interface import GPT4Interfacer, LLama3Interface
from natural20.gym.dndenv_controller import DndenvController
import os
import time

MAX_EPISODES = 20


prompt = GPT4Interfacer()
prompt2 = LLama3Interface("your endpoint here")

class CustomAgent:
    def __init__(self, llm_interface):
        self.llm_interface = llm_interface

    def step(self, observation, info):
        return self.llm_interface.select_action_for_state(observation, info)
    
    def __str__(self) -> str:
        return "Custom LLM Agent"

agent = CustomAgent(prompt2)
env = make("dndenv-v0", root_path="templates", render_mode="ansi", custom_agent=agent)

observation, info = env.reset(seed=42)

print("=========================================")
print("Battle between two LLM agents in a game of DnD")
print("=========================================")
action = prompt.select_action_for_state(observation, info)

print(f"selected action: {action}")
terminal = False
episode = 0
timestamp = time.strftime("%Y%m%d-%H%M%S")
output_folder = f"output_{timestamp}"


os.makedirs(output_folder, exist_ok=True)

while not terminal and episode < MAX_EPISODES:
    episode += 1
    observation, reward, terminal, truncated, info = env.step(action)
    if not terminal and not truncated:
        episode_name_with_padding = str(episode).zfill(3)

        with open(f"{output_folder}/battle_{episode_name_with_padding}.txt", "w") as f:
            # display entity healths
            f.write(f"Turn {info['current_index']}\n")
            f.write(f"Reward: {reward}\n")
            f.write(f"health hero: {observation['health_pct']}\n")
            f.write(f"health enemy: {observation['health_enemy']}\n")
            f.write(env.render())
        
        # action = random.choice(info['available_moves'])
        action = prompt.select_action_for_state(observation, info)
        print(f"selected action: {action}")

    if terminal or truncated:
        print(f"Reward: {reward}")
        break