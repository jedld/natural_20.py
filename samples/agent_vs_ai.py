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
from model import QNetwork
from natural20.gym.llm_helpers.prompting_utils import action_to_prompt
from natural20.gym.dndenv import embedding_loader
from natural20.event_manager import EventManager
import os
import time
import torch
import random
import pdb


MAX_EPISODES = 500

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

class ModelPolicy:
    def __init__(self, session, debug=False):
        self.session = session
        self.weapon_mappings, self.spell_mappings, self.entity_mappings = embedding_loader(self.session)
        if self.weapon_mappings is None or self.spell_mappings is None:
            raise ValueError("Embeddings not loaded")
        self.debug = debug
        self.model = QNetwork(device=device)
        self.model.to(device)
        fname = "samples/model_best_dnd_egreedy.pt"
        if not os.path.exists(fname):
            raise FileNotFoundError(f"Model file {fname} not found. Please run dnd_dqn.ipynb notebook to train an agent.")
        self.model.load_state_dict(torch.load(fname))

    def action(self, state, info):
        available_moves = info["available_moves"]
        values = torch.stack([self.model(state, move) for move in available_moves])
        if self.debug:
            for index, v in enumerate(values):
                description = action_to_prompt(available_moves[index], self.weapon_mappings, self.spell_mappings)
                print(f"{index}: {description} {v.item()}")

        chosen_index = torch.argmax(values).item()
        if self.debug:
            print(f"Chosen index: {chosen_index}")
        return available_moves[chosen_index]


# setup event manager so that we can see combat logs shown in the console
event_manager = EventManager()
event_manager.standard_cli()
session = Session(root_path="samples/map_with_obstacles", event_manager=event_manager)

# setup the environment
env = make("dndenv-v0", root_path="samples/map_with_obstacles", render_mode="ansi",
            show_logs=True,
            custom_session=session,
            profiles=lambda: random.choice([('high_elf_mage.yml','Joe'), \
                                            ('high_elf_fighter.yml','Joe'), \
                                            ('halfling_rogue.yml', 'Joe')]),
            enemies=lambda: random.choice([('high_elf_fighter.yml', 'Mike'),\
                                           ('halfling_rogue.yml','Mike')]),
            map_file=lambda: random.choice(['maps/simple_map', 'maps/complex_map', 'maps/game_map']))

# setup the model and policy wrapper
model = ModelPolicy(session, debug=True)

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
print("Battle between an RL agent vs a Rules based AI")
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