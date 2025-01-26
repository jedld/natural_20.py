
import random
from openai import OpenAI
import time
import os
import requests
import json
from natural20.gym.llm_helpers.prompting_utils import actions_to_prompt
import pdb

class LLMInterfacer:
    def __init__(self, debug=False, explain=False):
        self.debug = debug
        self.explain = explain

    def select_action_for_state(self, state, info):
        # just return a random action for now
        # trunk-ignore(bandit/B311)
        action = random.choice(info['available_moves']) # assign random action instead
        return action
    
    def action(self, observation, info):
        return self.select_action_for_state(observation, info)

    def dndenv_state_to_prompt(self, state, info):
        map = state["map"]
        actions, bonus_actions, reactions = state["turn_info"]
        player_type = state["player_type"][0]
        enemy_type = state["enemy_type"][0]

        entity_mappings = info["entity_mappings"]
        # swap values to keys for entity mappings
        entity_mappings = {v: k for k, v in entity_mappings.items()}
        player_type_str = entity_mappings.get(player_type, "")
        enemy_type_str = entity_mappings.get(enemy_type, "")
        # split class type and level from player_type_str separated by a  "-" for example fighter-1
        player_type_str, player_level = player_type_str.split("-")
        enemy_type_str, enemy_level = enemy_type_str.split("-")

        health_pct = state["health_pct"]
        health_enemy = state["health_enemy"]
        movement = state["movement"]

        conditions = state["conditions"]
        is_prone, is_dodging, is_grappled, is_disengaging, _, _, _, _ = conditions
        is_enemy_prone, is_enemy_dodging, is_enemy_grappled, is_enemy_disengaging, _, _, _, _  = state["enemy_conditions"]

        instruction_prompt = "We are playing a game of Dungeons and Dragons 5th Edition. It is current your turn and you play \n" + \
                             f"as a hero character denoted by P (a level {player_level} {player_type_str}). And you have an enemy donoted by E (a level {enemy_level} {enemy_type_str})which you must defeat. \n"
        instruction_prompt += f"Your health is at {health_pct*100}% specifically {info['health']}/{info['max_health']} \n"
        instruction_prompt += f"Your Enemies health is at {health_enemy*100}%\n"
        instruction_prompt += "Your current conditions are:\n"
        if is_prone:
            instruction_prompt += "Currently Prone\n"

        if is_dodging:
            instruction_prompt += "Currently Dodging\n"

        if is_disengaging:
            instruction_prompt += "Currently Disengaging\n"

        instruction_prompt += "Your enemies current conditions are:\n"
        if is_enemy_prone:
            instruction_prompt += "Currently Prone\n"

        if is_enemy_dodging:
            instruction_prompt += "Currently Dodging\n"

        if is_enemy_disengaging:
            instruction_prompt += "Currently Disengaging\n"

        instruction_prompt += "You have the following available actions and movement available:\n\n"
        instruction_prompt += f"Available movement: {movement}ft\n"
        instruction_prompt += f"Available actions: {actions}\n"
        instruction_prompt += f"Bonus actions: {bonus_actions}\n"
        instruction_prompt += f"Reactions: {reactions}\n\n"
        spell_slots = state["spell_slots"]
        for level, slots in enumerate(spell_slots):
            if slots > 0:
                instruction_prompt += f"Spell Slot Level {level + 1}: {slots} slots\n"
        prompt = instruction_prompt
        prompt += self.map_to_prompt(map)
        if info.get('trigger', False):
            prompt += f"Note that this is not really your turn but a Reaction for {info['trigger']}:"
        prompt += actions_to_prompt(info['available_moves'], info["weapon_mappings"], info["spell_mappings"])
        prompt += "\n\nPlease choose the number corresponding to the action you would like to take.\n"
        prompt += "Provide your answer using the format, starting with the desired number choice, followed by the colon and the action.\n"
        if self.explain:
            prompt += "Following that line, please provide an explanation of why you chose that action.\n"

        prompt + "See sample below:\n\n"
        prompt += "1: attack enemy with ranged weapon\n"

        if self.explain:
            prompt += "explanation: I attacked the enemy because he was low and health.\n"
        else:
            prompt += "Just provide the action choice, no need to explain.\n"

        return prompt

    def map_to_prompt(self, map):
        prompt =  "\n\nHere is a rough sketch of the map that considers line of sight to the enemy.\n"

        prompt += "Here is the map:\n"

        for row in map:
            row_str = ""
            for col in row:
                token = None

                entity_type, terrain, entity_int, health_pct, status = col

                if terrain == 255:
                    token = " "
                elif terrain == 1:
                    token = "."
                elif terrain == 2:
                    token = "*"
                elif terrain == 3:
                    token = "~"
                elif terrain == 4:
                    token = "o"
                elif terrain == 0:
                    token = "_"
                else:
                    raise ValueError(f"Invalid terrain value {terrain}")

                if entity_int == 1:
                    token = "P"
                elif entity_int == 2:
                    token = "E"
                elif entity_int == 3:
                    token = "A"
                elif entity_int == 4:
                    token = "?"

                row_str += token
            prompt += row_str + "\n"
        prompt +"\nHere is the legend for the map, note that each tile is 5ft by 5ft:\n"
        prompt += "areas with no characters are represented by a dot (.)\n"
        prompt += "the hero character is represented by a (P)\n"
        prompt += "the enemy character is represented by an (E)\n"
        prompt += "Allies or Party Members are represented by an (A)\n"
        prompt += "Neutral characters are represented by a question mark (?)\n"
        prompt += "areas outside of the map are represented by a hash (_), you cannot move to areas with _\n"
        prompt += "areas with obstacles are represented by an asterisk (*)\n"
        prompt += "areas with a barrel are represented by an (o). These provide half-cover if right behind it and attacks are comming from the other side.\n"
        prompt += "areas with water are represented by a tilde (~) and are difficult terrain\n"
        prompt += "areas that the player can't see are just blanks/space\n"
        prompt += "Each tile of the map is 5ft by 5ft.\n\n"
        return prompt

class OllamaInterfacer(LLMInterfacer):
    def __init__(self, url="http://localhost:11411/generate", model="llama2-7b", debug=False, explain=False):
        super().__init__(debug, explain=explain)
        self.url = url
        self.model = model

    def select_action_for_state(self, state, info):
        prompt = self.dndenv_state_to_prompt(state, info)
        try:
            response = requests.post(self.url, json={"prompt": prompt, "model": self.model})
            result = response.json()
            raw_text = result.get("completion", "")
            extracted = "".join(ch for ch in raw_text if ch.isdigit())
            choice = int(extracted[0]) if extracted else 0
        except:
            choice = 0
        return info["available_moves"][choice - 1] if choice > 0 else random.choice(info["available_moves"])


class GPT4Interfacer(LLMInterfacer):
    def __init__(self, variant="NousResearch/Meta-Llama-3-8B-Instruct", debug=False, api_key=None, base_url=None, tools=False, explain=False, weapon_mappings=None, max_retries=4):
        """
        Args:
            api_key: the openai api key to use
            variant: the variant of the model to use, e.g. gpt-4o, gpt-4, etc.
            debug: whether to print debug information
        """
        super().__init__(debug, explain=explain)

        if api_key is None and base_url is None:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key is None:
                raise ValueError("Please set the OPENAI_API_KEY environment variable")

        self.variant = variant
        self.debug = debug
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=max_retries
        )
        if tools:
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
        else:
            self.tools = None
    
    def select_action_for_state(self, state, info):
        prompt = self.dndenv_state_to_prompt(state, info)
        # measure gpt-4o response time
        start_time = time.time()

        if self.debug:
            print(f"prompt: -------------------------------\n{prompt}\n---------------------------------")
        if self.tools:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model=self.variant,
                tools=self.tools,
                tool_choice="required"
            )
        else:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model=self.variant
            )
        
        if self.tools:
            orig_response = chat_completion.choices[0].message.tool_calls[0].function.arguments
            
        else:
            orig_response = chat_completion.choices[0].message.content
            digit_response = ""

            # skip the initial non-digit characters
            encountered_digit = False

            for char in orig_response:
                if char.isdigit():
                    encountered_digit = True
                    digit_response += char
                else:
                    if encountered_digit:
                        break

        try:
            if self.tools:
                json_response = json.loads(orig_response)
                if self.debug:
                    print(json_response)
                digit_response = json_response['action']

            end_time = time.time()
            if self.debug:
                print(f"response time: {end_time - start_time}")

            if int(digit_response) == 0:
                action = (-1, (0, 0), (0, 0), 0, 0)
            else:
                action = info['available_moves'][int(digit_response) - 1]
        except Exception as e:
            print(e)
            print(f"unusual response: {orig_response}")
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
        # import json
        # Example usage
        regex = "\d"

        json_response = self._generate_text_with_regex(prompt, regex)

        #json_response = chat_completion.choices[0].message.tool_calls[0].function.arguments#json.loads(chat_completion.choices[0].message.function_call.arguments)
        #json_response = json.loads(json_response)
        response = self._extract_last_number(json_response['text'][0])

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
                action = (-1, (0, 0), (0, 0), 0, 0)
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
        print(response)
        if response.status_code == 200:
            return response.json()
        else:
            print(response.text)
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


        


    


        