A Dungeons and Dragons game engine that can be used for AI related research

This project provides a complete Gymnasium compatible environment for performing
AI related research on the Dungeons and Dragons 5th edition RPGs.

Installation
============

This environment works with Gymnasium

Installing Gym
--------------

You can install the Gymnasium library using pip:

```
gymnasium
```

For development you may run the prequisite libraries using:

```
pip install -r requirements.txt
```

Quickstart
==========

Here is a simple example to get started with gym-dndenv. Below is an example demonstrates how to create the environment for testing battles against LLMs (e.g. GPT-4), reset it for the initial observation, and interact with it using a language model interfacer:


```python
from gymnasium import make
from llm_interface import GPT4Interfacer

MAX_EPISODES = 20

# Initialize the environment
env = make("dndenv-v0", root_path="templates", render_mode="ansi")
observation, info = env.reset(seed=42)

# Initialize your language model interfacer
prompt = GPT4Interfacer(debug=True)

# Select an action based on the initial state
action = prompt.select_action_for_state(observation, info)
print(f"Selected action: {action}")

terminal = False
episode = 0
while not terminal and episode < MAX_EPISODES:
    episode += 1
    observation, reward, terminal, truncated, info = env.step(action)
    if not terminal and not truncated:
        print(env.render())
        action = prompt.select_action_for_state(observation, info)
        print(f"Selected action: {action}")

    if terminal or truncated:
        print(f"Reward: {reward}")
        break
```

Samples
=======

Please see the samples directory for more samples.



Running Tests
=============

```python
python -m unittest discover tests
```

Run specific tests

```
python -m unittest tests.test_gym.TestGym.test_reset
python -m unittest tests.test_map.TestMap.test_line_of_sight
```