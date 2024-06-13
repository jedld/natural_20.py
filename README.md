A Dungeons and Dragons game engine that can be used for AI related research

This project provides a complete Gymnasium compatible environment for performing
AI related research on the Dungeons and Dragons 5th edition RPGs.

Features
========

- Simulation of DnD Maps, Line of Sight Computations, Cover
- Character classes (Fighter, Rogue & Mage)
- Weapons and Spells systems
- Text-based interface with ability to be used as a backend for web based interfaces.



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

Dice Rolls
==========

Natural20.py comes with a complete Dungeons and Dragons die rolls simulator that you can use for other projects.

## DieRoll Class Usage

The `DieRoll` class provides a powerful and flexible way to handle dice rolls within tabletop RPGs and similar games. Below are examples on how to utilize this class effectively in your game sessions.

### Basic Usage

```python
from natural20.die_roll import DieRoll

# Rolling a single d20 die
result = DieRoll.roll('1d20').result()
print("Result of a d20 roll: ", result)
# Result of a d20 roll:  7

# Rolling two d6 dice with a +2 modifier
result = DieRoll.roll('2d6+2').result()
print("Result of 2d6 + 2: ", result)


# Rolling with advantage
advantage_roll = DieRoll.roll('1d20', advantage=True)
print("Roll with advantage: ", advantage_roll)
# Roll with advantage:  (5 | 15)

# Rolling with disadvantage
disadvantage_roll = DieRoll.roll('1d20', disadvantage=True)
print("Roll with disadvantage: ", disadvantage_roll)
# Roll with disadvantage:  (15 | 3)

# Critical hit dice rolls e.g. indicated Die are rolled twice
critical_roll = DieRoll.roll('1d6', crit=True)
print("Critical roll (double dice): ", critical_roll)
# Critical roll (double dice):  (5 + 1)

# Expected value of rolling 1d6 + 2
expected_value = DieRoll.roll('1d6+2').expected()
print("Expected value of 1d6 + 2: ", expected_value)
# Expected value of 1d6 + 2:  5.5

# Probability of rolling at least 10 on 1d20+5
probability = DieRoll.roll('1d20+5').prob(10)
print("Probability of rolling at least 10 on 1d20+5: ", round(probability, 2))
# Probability of rolling at least 10 on 1d20+5:  0.8
```

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