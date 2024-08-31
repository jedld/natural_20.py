from gymnasium import make
from llm_interface import GPT4Interfacer
import random
import os

MAX_EPISODES = 500
USE_OPENAI = True

env = make("dndenv-v0", root_path="samples/map_with_obstacles",
           render_mode="ansi",
           profiles=lambda: random.choice(['high_elf_fighter']),
                enemies=lambda: random.choice(['high_elf_fighter']),
                map_file=lambda: random.choice(['maps/simple_map',\
                                                'maps/complex_map', \
                                                'maps/game_map', \
                                                'maps/walled_map']),
           debug=True,
           show_logs=True)


# variant = 'NousResearch/Meta-Llama-3.1-8B-Instruct'
VARIANT = 'mistralai/Mistral-7B-Instruct-v0.3'

# Check option to use a local LLM model served via VLLM or the OpenAI API
# prompt = LLama3Interface("http://202.92.159.241:8000/generate", debug=True)

if not USE_OPENAI:
    URL = os.getenv("OPENAI_BASE_URL", "http://202.92.159.242:8000/v1")

    if not URL:
        raise ValueError("Please set the OPENAI_BASE_URL environment variable")
    # prompt = GPT4Interfacer(debug=True, tools=False, base_url=URL, api_key="token1234", variant="NousResearch/Meta-Llama-3-8B-Instruct")
    prompt = GPT4Interfacer(debug=True, tools=False, base_url=URL, api_key="token1234", variant=VARIANT)
else:
    prompt = GPT4Interfacer(debug=True, variant="gpt-4o", tools=True)

def reaction_callback(state, reward, done, truncated, info):
    """
    Callback function to be called when the environment is waiting for a reaction from the agent.
    Reactions in DnD are typically reactions to enemy actions, such as opportunity attacks.
    """
    print(f"{info['reactor']}: Reaction for {info['trigger']}:")
    action = prompt.select_action_for_state(state, info)
    return action

wins = 0
losses = 0
ties = 0

for i in range(30):
    print(f"***** Episode {i + 1} *****")

    observation, info = env.reset(reaction_callback=reaction_callback)

    # prompt = GPT4Interfacer(debug=True, base_url=URL, api_key="token1234", variant="NousResearch/Meta-Llama-3-8B-Instruct", tools=False)

    # prompt = LLama3Interface(URL, debug=True)
    action = prompt.select_action_for_state(observation, info)

    print(f"selected action: {action}")
    terminal = False
    episode = 0
    while not terminal and episode < MAX_EPISODES:
        episode += 1
        observation, reward, terminal, truncated, info = env.step(action)
        if not terminal and not truncated:
            print(env.render())
            # action = random.choice(info['available_moves'])
            action = prompt.select_action_for_state(observation, info)
            print(f"selected action: {action}")

        if terminal or truncated:
            print(f"Reward: {reward}")
            if reward == 10:
                wins += 1
            elif reward == -10:
                losses += 1
            else:
                ties += 1
            break

print(f"Wins: {wins}, Losses: {losses}, Ties: {ties}")