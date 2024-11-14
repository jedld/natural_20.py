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
import os
import time
import random
from natural20.event_manager import EventManager

MAX_EPISODES = 20

LLAMA3_URL = "http://localhost:8001/v1"
VARIANT = 'gpt-4o'
BACKUP_VARIANT = 'NousResearch/Meta-Llama-3.1-8B-Instruct'

prompt = GPT4Interfacer(debug=True, tools=True, api_key="OPENAI_TOKEN", variant=VARIANT, explain=False)

prompt2 = GPT4Interfacer(debug=True, tools=False, base_url=LLAMA3_URL, api_key="token1234", variant=BACKUP_VARIANT)


class CustomAgent:
    def __init__(self, llm_interface):
        self.llm_interface = llm_interface

    def action(self, observation, info):
        return self.llm_interface.select_action_for_state(observation, info)
    
    def __str__(self) -> str:
        return "Custom LLM Agent"

agent = CustomAgent(prompt2)

# setup event manager so that we can see combat logs shown in the console
event_manager = EventManager()
event_manager.standard_cli()
session = Session(root_path="samples/map_with_obstacles", event_manager=event_manager)


env = make("dndenv-v0", root_path="samples/map_with_obstacles", render_mode="ansi",
            show_logs=True,
            custom_session=session,
            custom_agent=agent,
            profiles=lambda: random.choice([('high_elf_mage.yml','Joe'), \
                                            ('high_elf_fighter.yml','Joe'), \
                                            ('halfling_rogue.yml', 'Joe'),
                                            ('dwarf_cleric.yml', 'Joe')]),
            enemies=lambda: random.choice([('high_elf_fighter.yml', 'Mike'),\
                                           ('halfling_rogue.yml','Mike'),\
                                           ('dwarf_cleric.yml', 'Mike'),\
                                           ('high_elf_mage.yml', 'Mike')]),
            map_file=lambda: random.choice(['maps/simple_map',\
                                            'maps/complex_map',\
                                                'maps/game_map',\
                                                'maps/walled_map']))

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