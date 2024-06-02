
import random
from openai import OpenAI
from natural20.gym.dndenv import dndenv, action_type_to_int
import time
import json
import os
import re
import requests

class LLMInterfacer:
    def __init__(self, debug=False):
        self.debug = debug

    def select_action_for_state(self, state, info):
        # just return a random action for now
        action = random.choice(info['available_moves']) # assign random action instead
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
        prompt += "\n\nPlease choose the number corresponding to the action you would like to take.\n"
        prompt += "Provide the number as your first answer in the following format, for example:\n"
        prompt += "1: attack enemy with ranged weapon\n"
        prompt += "No need to explain just provide the answer."
        return prompt
    
    def action_to_prompt(self, actions):
        prompt = "\n\nHere are the available actions you can take, please choose the number corresponding to the action:\n"
        prompt += "0: end my turn\n"
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
        prompt += "areas outside of the map are represented by a hash (_), you cannot move to areas with _\n"
        prompt += "areas with obstacles are represented by an asterisk (*)\n"
        prompt += "Each tile of the map is 5ft by 5ft\n"
        prompt += "Here is the map:\n"

        for row in map:
            row_str = ""
            for col in row:
                token = None
                entity, terrain, health_pct = col

                if terrain == -1:
                    token = "_"
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
    

class GPT4Interfacer(LLMInterfacer):
    def __init__(self, variant="gpt-4o", debug=False):
        """
        Args:
            api_key: the openai api key to use
            variant: the variant of the model to use, e.g. gpt-4o, gpt-4, etc.
            debug: whether to print debug information
        """
        super().__init__(debug)
        
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key is None:
            raise ValueError("Please set the OPENAI_API_KEY environment variable")
        
        self.variant = variant
        self.debug = debug
        self.client = OpenAI(
            # This is the default and can be omitted
            api_key=api_key
        )
        self.tools = [
            {
                "type": "function",
                "function": {
                "name": "get_action",
                "description": "get action for agent to execute",
                "parameters": {
                    "type": "object",
                    "properties": {
                    "action": {
                        "type": "integer",
                        "description": "action to take",
                    }
                    },
                    "required": ["action"],
                },
                }
            }
        ]
    
    def select_action_for_state(self, state, info):
        prompt = self.dndenv_state_to_prompt(state, info)
        # measure gpt-4o response time
        start_time = time.time()

        if self.debug:
            print(f"prompt: -------------------------------\n{prompt}\n---------------------------------")
        chat_completion = self.client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model=self.variant,
            
            # add the action function to the completion
        tools=self.tools,
            tool_choice="required"
        )
        
        #response = chat_completion.choices[0].message.content

        json_response = chat_completion.choices[0].message.tool_calls[0].function.arguments#json.loads(chat_completion.choices[0].message.function_call.arguments)
        json_response = json.loads(json_response)
        print(json_response)
        response = json_response['action']
        
        end_time = time.time()
        if self.debug:
            print(f"response time: {end_time - start_time}")
            print(f"response: {response}")
        # parse the response and return the action
        # e.g. 1: attack enemy with ranged weapon or Let's proceed with option [4], or just extract the first number
        # from the response

        #for char in response:
        #    if char.isdigit():
        #        response = char
        #        break 

        try:
            print(f"response: {response}")
            if int(response) == 0:
                action = (-1, (0, 0), (0, 0), 0)
            else:
                action = info['available_moves'][int(response) - 1]
        except Exception as e:
            print(e)
            print(f"unusual response: {response}")
            action = random.choice(info['available_moves']) # assign random action instead
        return action
    

class LLama3Interface(LLMInterfacer):
    def __init__(self, url, debug=False):
        super().__init__(debug)
        self.url = url

    def select_action_for_state(self, state, info):
        prompt = self.dndenv_state_to_prompt(state, info)
        # measure gpt-4o response time
        start_time = time.time()

        if self.debug:
            print(f"prompt: -------------------------------\n{prompt}\n---------------------------------")
        #chat_completion = self.client.chat.completions.create(
        #    messages=[
        #        {
        #            "role": "user",
        #            "content": prompt,
        #        }
        #    ],
        #    model="gpt-4o",
            
            # add the action function to the completion
        #   tools=tools,
        #    tool_choice="required"
        #)
        
        #response = chat_completion.choices[0].message.content
        import json
        # Example usage
        regex = "\d"

        json_response = self._generate_text_with_regex(prompt, regex)
        
        #json_response = chat_completion.choices[0].message.tool_calls[0].function.arguments#json.loads(chat_completion.choices[0].message.function_call.arguments)
        #json_response = json.loads(json_response)
        print("*"*50)
        print(json_response['text'][0])
        print("*"*50)
        response = self._extract_last_number(json_response['text'][0])
        print(response)
        #response = json_response['action']
        
        end_time = time.time()
        if self.debug:
            print(f"response time: {end_time - start_time}")
            print(f"response: {response}")
        # parse the response and return the action
        # e.g. 1: attack enemy with ranged weapon or Let's proceed with option [4], or just extract the first number
        # from the response

        #for char in response:
        #    if char.isdigit():
        #        response = char
        #        break 

        try:
            print(f"response: {response}")
            if int(response) == 0:
                action = (-1, (0, 0), (0, 0), 0)
            else:
                action = info['available_moves'][int(response) - 1]
        except Exception as e:
            print(e)
            print(f"unusual response: {response}")
            action = random.choice(info['available_moves']) # assign random action instead
        return action
    
    def _generate_text_with_regex(self, prompt, regex):
        data = {
            "prompt": prompt,
            "regex": regex
        }
        
        response = requests.post(self.url, json=data)
        
        if response.status_code == 200:
            return response.json()
        else:
            return None



    def _extract_last_number(self, text):
        # Regular expression to match numbers
        #number_regex = r'-?\d+(\.\d+)?'
        
        # Find all matches in the text
        text = text.split(".")[-1]
        #print("hello: ",text)

        # matches = re.findall(number_regex, text)
        
        # Return the last match or None if no match is found
        #return matches if matches else None
        return int(text)


        


    


        