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
from openai import OpenAI
import time

import random

class StateToPrompt:
    def __init__(self, api_key, debug=False):
        self.debug = debug
        self.client = OpenAI(
            # This is the default and can be omitted
            api_key=api_key
        )

    def select_action_for_state(self, state, info):
        prompt = self.dndenv_state_to_prompt(state, info)
        # measure gpt-4o response time
        start_time = time.time()

        if self.debug:
            print(f"prompt: {prompt}")
        chat_completion = self.client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="gpt-4o",
        )
        response = chat_completion.choices[0].message.content
        end_time = time.time()
        if self.debug:
            print(f"response time: {end_time - start_time}")
            print(f"response: {response}")
        # parse the response and return the action
        # e.g. 1: attack enemy with ranged weapon or Let's proceed with option [4], or just extract the first number
        # from the response

        for char in response:
            if char.isdigit():
                response = char
                break 

        try:
            print(f"response: {response}")
            action = info['available_moves'][int(response) - 1]
        except:
            print(f"unusual response: {response}")
        return action


    def dndenv_state_to_prompt(self, state, info):
        map = state["map"]
        actions, bonus_actions, reactions = state["turn_info"]

        health_pct = state["health_pct"]
        movement = state["movement"]
        instruction_prompt = "We are playing a game of Dungeons and Dragons 5th Edition. It is current your turn and you play \n" + \
                             "as a hero character denoted by P. And you have an enemy donoted by E which you must defeat. \n"
        instruction_prompt += f"Your health is at {health_pct*100}%\n"
        instruction_prompt += "You have the following available actions and movement available:\n\n"
        instruction_prompt += f"Available movement: {movement}ft\n"
        instruction_prompt += f"Available actions: {actions}\n"
        instruction_prompt += f"Bonus actions: {bonus_actions}\n"
        instruction_prompt += f"Reactions: {reactions}\n\n"
        prompt = instruction_prompt        
        prompt += self.map_to_prompt(map)
        prompt += self.action_to_prompt(info['available_moves'])
        prompt += "\n\nPlease choose the number corresponding to the action you would like to take. No need to explain and elaborate.\n"
        return prompt
    
    def action_to_prompt(self, actions):
        prompt = "\n\nHere are the available actions you can take, please choose the number corresponding to the action:\n"
        for index, action in enumerate(actions):
            action_type, param1, param2, param3 = action
            if action_type == action_type_to_int("move"):
                message = f"move 5ft "
                x, y = param1
                if (x < 0 and y==0):
                    message += f"to the left\n"
                elif (x > 0 and y==0):
                    message += f"to the right\n"
                elif (x == 0 and y < 0):
                    message += f"up\n"
                elif (x == 0 and y > 0):
                    message += f"down\n"
                elif (x < 0 and y < 0):
                    message += f"up and to the left\n"
                elif (x < 0 and y > 0):
                    message += f"down and to the left\n"
                elif (x > 0 and y < 0):
                    message += f"up and to the right\n"
                elif (x > 0 and y > 0):
                    message += f"down and to the right\n"

                
            elif action_type == action_type_to_int("attack"):
                message = f"attack enemy "
                if param3 == 1:
                    message += f"with ranged weapon\n"
                else:
                    message += f"with melee weapon\n"
            elif action_type == action_type_to_int("dash"):
                message = f"dash action\n"
            elif action_type == action_type_to_int("disengage"):
                message = f"disengage action\n"
            elif action_type == action_type_to_int("dodge"):
                message = f"dodge action\n"
            elif action_type == action_type_to_int("help"):
                message = f"help action\n"
            elif action_type == action_type_to_int("hide"):
                message = f"hide action\n"
            elif action_type == action_type_to_int("stand"):
                message = f"stand action\n"
            elif action_type == action_type_to_int("second_wind"):
                message = f"second wind action\n"
            else:
                message = f"unknown action {action_type}\n"
                raise ValueError(f"Unknown action type {action_type}")

            prompt += f"{index + 1}: {message}\n"
        return prompt

    def map_to_prompt(self, map):
        prompt =  "\n\nHere is a rough sketch of the map that considers line of sight to the enemy. The legend is followed by a sketch of a map tile in each line:\n"
        prompt += "areas with no characters are represented by a dot (.)\n"
        prompt += "the hero character is represented by a P\n"
        prompt += "the enemy character is represented by an E\n"
        prompt += "areas outside of the map are represented by a hash (#)\n"
        prompt += "areas with obstacles are represented by an asterisk (*)\n"
        prompt += "Each tile of the map is 5ft by 5ft\n"
        prompt += "Here is the map:\n"

        for row in map:
            row_str = ""
            for col in row:
                token = None
                entity, terrain, health_pct = col

                if terrain == -1:
                    token = "#"
                elif terrain == 1:
                    token = "*"
                elif terrain == 0:
                    token = "."
                else:
                    raise ValueError(f"Invalid terrain value {terrain}")

                if entity == 1:
                    token = "P"
                elif entity == 2:
                    token = "E"
                
                row_str += token
            prompt += row_str + "\n"

        return prompt


MAX_EPISODES = 100

api_key='OPEN AI KEY HERE'
env = make("dndenv-v0", root_path="templates", render_mode="ansi")
observation, info = env.reset(seed=42)

prompt = StateToPrompt(api_key=api_key, debug=False)
action = prompt.select_action_for_state(observation, info)
print(f"selected action: {action}")

terminal = False
episode = 0

while not terminal and episode < MAX_EPISODES:
    observation, reward, terminal, truncated, info = env.step(action)
    if not terminal and not truncated:
        action = prompt.select_action_for_state(observation, info)
        # print(f"selected action: {action}")
        print(env.render())
    if terminal or truncated:
        print(f"Reward: {reward}")
        break