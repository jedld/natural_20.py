import unittest
from natural20.map import Map, Terrain
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.map_renderer import MapRenderer
from natural20.die_roll import DieRoll
from natural20.generic_controller import GenericController
from natural20.session import Session
from natural20.actions.move_action import MoveAction
from natural20.action import Action
from natural20.gym.dndenv import dndenv, action_type_to_int
from gymnasium import register, envs, make
from llm_interface import GPT4Interfacer, LLama3Interface
from natural20.gym.dndenv_controller import DndenvController
from model import ModelPolicy

from natural20.gym.dndenv import embedding_loader
from natural20.event_manager import EventManager
import os
import time
import torch
import random
import pdb


MAX_EPISODES = 500
USE_OPENAI = True
MODEL_PATH = "samples/model_best_dnd_egreedy.pt"

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

if not USE_OPENAI:
    URL = os.getenv("OPENAI_BASE_URL", "http://localhost:8000/v1")

    if not URL:
        raise ValueError("Please set the OPENAI_BASE_URL environment variable")
    prompt = GPT4Interfacer(debug=True, tools=False, base_url=URL, api_key="token1234", variant="NousResearch/Meta-Llama-3-8B-Instruct", explain=False)
else:
    prompt = GPT4Interfacer(debug=True, variant="gpt-4o", tools=True, explain=False)


# setup event manager so that we can see combat logs shown in the console
event_manager = EventManager()
event_manager.standard_cli()
session = Session(root_path="samples/map_with_obstacles", event_manager=event_manager)

class CustomAgent:
    def __init__(self, llm_interface):
        self.llm_interface = llm_interface

    def step(self, observation, info):
        return self.llm_interface.select_action_for_state(observation, info)

    def __str__(self) -> str:
        return "Custom LLM Agent"

agent = CustomAgent(prompt)


# setup the environment
env = make("dndenv-v0", root_path="samples/map_with_obstacles", render_mode="ansi",
            show_logs=True,
            custom_session=session,
            custom_agent=agent,
            profiles=lambda: random.choice([('high_elf_mage.yml','Joe'), \
                                            ('high_elf_fighter.yml','Joe'), \
                                            ('halfling_rogue.yml', 'Joe')]),
            enemies=lambda: random.choice([('high_elf_fighter.yml', 'Mike'),\
                                           ('halfling_rogue.yml','Mike')]),
            map_file=lambda: random.choice(['maps/simple_map',\
                                            'maps/complex_map',\
                                                'maps/game_map',\
                                                'maps/walled_map']))

# setup the model and policy wrapper for the RL agent
model = ModelPolicy(session, debug=True, model_path=MODEL_PATH, device=device)

def reaction_callback(state, reward, done, truncated, info):
    """
    Callback function to be called when the environment is waiting for a reaction from the agent.
    Reactions in DnD are typically reactions to enemy actions, such as opportunity attacks.
    """
    print(f"{info['reactor']}: Reaction for {info['trigger']}:")
    action = model.action(state, info)
    return action

observation, info = env.reset(reaction_callback=reaction_callback)

print("=========================================")
print("Battle between an RL agent vs a LLM agent")
print("=========================================")
print(env.render())

action = model.action(observation, info)

print(f"selected action: {action}")
terminal = False
episode = 0
timestamp = time.strftime("%Y%m%d-%H%M%S")
output_folder = f"output_agent_vs_ai_{timestamp}"

os.makedirs(output_folder, exist_ok=True)

while not terminal and episode < MAX_EPISODES:
    episode += 1
    observation, reward, terminal, truncated, info = env.step(action)
    print(env.render())
    if not terminal and not truncated:
        episode_name_with_padding = str(episode).zfill(3)

        with open(f"{output_folder}/battle_{episode_name_with_padding}.txt", "w") as f:
            # display entity healths
            f.write(f"Turn {info['current_index']}\n")
            f.write(f"Reward: {reward}\n")
            f.write(f"health hero: {observation['health_pct']}\n")
            f.write(f"health enemy: {observation['health_enemy']}\n")
            f.write(env.render())

        action = model.action(observation, info)

    if terminal or truncated:
        print(f"Reward: {reward}")
        break