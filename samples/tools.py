from gymnasium import make
from llm_interface import GPT4Interfacer

MAX_EPISODES = 20

env = make("dndenv-v0", root_path="templates", render_mode="ansi")
observation, info = env.reset(seed=42)

prompt = GPT4Interfacer(debug=True)
# prompt = LLama3Interface("http://202.92.159.241:8000/generate", debug=True)
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
        break