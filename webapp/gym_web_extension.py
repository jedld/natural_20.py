from flask import Flask
from natural20.session import Session
from natural20.gym.dndenv import dndenv, action_type_to_int
from gymnasium import register, envs, make
from natural20.player_character import PlayerCharacter
from natural20.gym.llm_helpers.prompting_utils import action_to_prompt
from natural20.gym.dndenv import embedding_loader
from natural20.event_manager import EventManager
from natural20.gym.dqn.policy import ModelPolicy
from samples.llm_interface import GPT4Interfacer
from natural20.map import Map
from natural20.battle import Battle
from natural20.gym.dndenv_controller import DndenvController
from webapp.controller.web_controller import WebController, ManualControl
import torch
import random
import numpy as np
import os

WEIGHTS_FOLDER = "model"
LLAMA3_URL =  os.getenv('LLAMA3_URL')
MISTRAL_URL = os.getenv('MISTRAL_URL')
GPT4_TOKEN = os.getenv('OPENAI_TOKEN')

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

class Agent:
    def action(self, observation, info):
        return random.choice(info['available_moves'])

class CustomAgent(Agent):
    def __init__(self, llm_interface):
        self.llm_interface = llm_interface

    def action(self, observation, info):
        return self.llm_interface.select_action_for_state(observation, info)
    def __str__(self) -> str:
        return "Custom LLM Agent"

class ModelAgent(Agent):
    def __init__(self, model_policy):
        self.model_policy = model_policy

    def action(self, observation, info):
        return self.model_policy.action(observation, info)

def prompt_for_variant(variant):
    if variant == "llama3":
        prompt = GPT4Interfacer(debug=False, tools=False, base_url=LLAMA3_URL, api_key="token1234", variant='NousResearch/Meta-Llama-3.1-8B-Instruct')
    elif variant == "gpt4":
        prompt = GPT4Interfacer(debug=False, tools=True, api_key=GPT4_TOKEN, variant='gpt-4o-mini')
    elif variant == "mistral":
        prompt = GPT4Interfacer(debug=False, tools=False, base_url=MISTRAL_URL, api_key="token1234", variant='mistralai/Mistral-7B-Instruct-v0.3')
    else:
        raise ValueError(f"Invalid variant: {variant}")

    return prompt

def create_agent(session, adversary):
    if adversary == "rl_rules_trained":
        model = ModelPolicy(session, weights_file=f"{WEIGHTS_FOLDER}/model_best_dnd_egreedy.pt", device=device, debug=False)
        adversary_agent = ModelAgent(model)
    elif adversary == "rl_llama3_trained":
        model = ModelPolicy(session, weights_file=f"{WEIGHTS_FOLDER}/model_best_llm_adversary.pt", device=device, debug=False)
        adversary_agent = ModelAgent(model)
    elif adversary == "rl_mistral_trained":
        model = ModelPolicy(session, weights_file=f"{WEIGHTS_FOLDER}/model_best_llm_adversary_mistral.pt", device=device, debug=False)
        adversary_agent = ModelAgent(model)
    elif adversary == "rl_gpt4_trained":
        model = ModelPolicy(session, weights_file=f"{WEIGHTS_FOLDER}/model_best_llm_adversary_gpt4.pt", device=device, debug=False)
        adversary_agent = ModelAgent(model)
    elif adversary.startswith("llm"):
        prompt = prompt_for_variant(adversary.split("_")[1])
        adversary_agent = CustomAgent(prompt)
    elif adversary == "ai":
        adversary_agent = None
    elif adversary == "random":
        adversary_agent = Agent()
    else:
        raise ValueError(f"Invalid adversary: {adversary}")
    
    return adversary_agent

def start_battle(game_manager, session):
    map_locations = random.choice(['maps/complex_map','maps/simple_map', 'maps/walled_map', 'maps/game_map'])
    available_agents = ["rl_rules_trained"]
    player_agent = create_agent(session, np.random.choice(available_agents))

    player_profile = random.choice(['high_elf_fighter','halfling_rogue','high_elf_mage','dwarf_cleric'])
    adversary_profile = random.choice(['high_elf_fighter','halfling_rogue','high_elf_mage','dwarf_cleric'])
    map = Map(session, map_locations, name=map_locations)
    battle = Battle(session, map, animation_log_enabled=True)
    player = PlayerCharacter.load(session, f'characters/{player_profile}', override={ 'display_name': f'Player ({player_profile})', 'entity_uid' : 'player' })

    adversary = PlayerCharacter.load(session, f'characters/{adversary_profile}', override={ 'display_name': f'Adversary ({adversary_profile})', 'entity_uid' : 'adversary' })
    controller = DndenvController(session, player_agent)
    controller.register_handlers_on(adversary)

    web_controller = WebController(session, "dm")
    web_controller.register_handlers_on(player)

    player_pos = None
    while player_pos is None or not map.placeable(player, player_pos[0], player_pos[1], squeeze=False):
        # trunk-ignore(bandit/B311)
        player_pos = [random.randint(0, map.size[0] - 1), random.randint(0, map.size[1] - 1)]
    print(f"player_pos = {player_pos}")
    battle.add(player, 'a', position=player_pos, token='A', add_to_initiative=True, controller=web_controller)
    player.reset_turn(battle)
    enemy_pos = None

    while enemy_pos is None or not map.placeable(adversary, enemy_pos[0], enemy_pos[1], squeeze=False):
        # trunk-ignore(bandit/B311)
        enemy_pos = [random.randint(0, map.size[0] - 1), random.randint(0, map.size[1] - 1)]
    print(f"enemy_pos = {enemy_pos}")
    battle.add(adversary, 'b', position=enemy_pos, token='B', add_to_initiative=True, controller=controller)
    adversary.reset_turn(battle)
    battle.start()

    game_manager.set_current_battle_map(map)
    game_manager.set_current_battle(battle)
    game_manager.refresh_client_map()
    return True

def _on_session_ready(game_manager, session):
    start_battle(game_manager, session)
    game_manager.execute_game_loop()

def _on_battle_end(game_manager, session):
    print("battle ended")
    battle = game_manager.get_current_battle()
    if 'a' in battle.winning_groups():
        winner_msg = "Player won!"
    else:
        winner_msg = "Adversary won!"

    game_manager.push_animation()

    def restart_callback(x):
        start_battle(game_manager, session)
        game_manager.execute_game_loop()

    game_manager.prompt(f"Battle ended {winner_msg}. Starting new battle...",
                        callback=restart_callback)

    return True

def init(app: Flask, game_manager, session):
    print("extension started")
    game_manager.register_event_handler('start_battle', start_battle)
    game_manager.register_event_handler('on_session_ready', _on_session_ready)
    game_manager.register_event_handler('on_battle_end', _on_battle_end)