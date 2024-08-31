import os
import time
import torch
import random
import numpy as np
import pandas as pd
import torch.optim as optim
import torch.nn as nn
import matplotlib.pyplot as plt
from gymnasium import register, envs, make
from collections import deque
from llm_interface import GPT4Interfacer, LLama3Interface
from model import QNetwork
from time import time as current_time
from natural20.gym.dqn.replay_buffer import ReplayBuffer

MAX_EPISODES = 20
BUFFER_CAPACITY = 3000
BATCH_SIZE = 32
MAX_STEPS = 500
EPSILON_START = 1.0
EPSILON_FINAL = 0.02
EPSILON_DECAY_FRAMES = 10**3
GAMMA = 0.99
LEARNING_RATE = 0.001
TARGET_UPDATE_FREQ = 10
T_HORIZON = 500

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    
class DQNAgent:
    def __init__(self, model, epsilon):
        self.model = model
        self.epsilon = epsilon

    def step(self, state, available_moves):
        if random.random() < self.epsilon:
            return random.choice(available_moves)
        else:
            values = torch.stack([self.model(state, move) for move in available_moves])
            return available_moves[torch.argmax(values).item()]

    def update_epsilon(self, step, decay_frames):
        self.epsilon = max(EPSILON_FINAL, EPSILON_START - (EPSILON_START - EPSILON_FINAL) * step / decay_frames)
    
    def __str__(self):
        return "DQN Agent"

class CustomAgent:
    def __init__(self, llm_interface):
        self.llm_interface = llm_interface

    def step(self, observation, info):
        return self.llm_interface.select_action_for_state(observation, info)
    
    def __str__(self):
        return "Custom LLM Agent"

def extract_features(state_dicts):
    return np.array([list(state.values()) for state in state_dicts])

def train_dqn(model, target_model, buffer, optimizer):
    if len(buffer) < BATCH_SIZE:
        return

    states, actions, rewards, infos, dones = buffer.sample(BATCH_SIZE)

    for i in range(len(states)):
        s = states[i]
        a = actions[i]

        r = torch.tensor(rewards[i]).to(device).unsqueeze(1)
        is_terminal = torch.tensor(dones[i]).float().to(device).unsqueeze(1)

        with torch.no_grad():
            s_next = s[1:]
            a_next = a[1:]
            q_targets = target_model.forward(s_next, a_next, pre_converted=True, pre_converted_action=True).detach()

        targets = r + GAMMA * q_targets * (1 - is_terminal)
        s_input = s[0:-1]
        a_input = a[0:-1]
        output = model.forward(s_input, a_input, pre_converted=True, pre_converted_action=True)
        q_sa = output

        value_loss = nn.MSELoss()(q_sa, targets)
        optimizer.zero_grad()
        value_loss.backward()
        optimizer.step()

def main():
    # prompt = GPT4Interfacer()
    prompt2 = LLama3Interface("http://202.92.159.241:8000/generate")

    env = make("dndenv-v0", root_path="templates", render_mode="ansi")

    model = QNetwork(device=device).to(device)
    target_model = QNetwork(device=device).to(device)
    target_model.load_state_dict(model.state_dict())

    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)
    buffer = ReplayBuffer(BUFFER_CAPACITY)

    epsilon = EPSILON_START
    dqn_agent = DQNAgent(model, epsilon)
    llm_agent = CustomAgent(prompt2)

    metrics = {
        "Episode": [],
        "Win/Loss Ratio": [],
    #    "Average Damage Dealt": [],
        "Survival Rate": [],
        "Time to Decision": [],
        "Performance Improvement Rate": [] ,
        "Total Rewards": [] 
       # "Efficiency Score": []
    }

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_folder = f"output_{timestamp}-llama"
    os.makedirs(output_folder, exist_ok=True)

    total_rewards = 0
    win_count = 0
    #total_damage_dealt = 0
    total_decision_time = 0
    survival_count = 0

    for episode in range(1, MAX_EPISODES + 1):
        observations = []
        actions = []
        rewards = []
        next_observations =[]
        terminals = []
        total_rewards = 0

        for _ in range(T_HORIZON):
          observation, info = env.reset(seed=42)
          terminal = False
          while not terminal:
              available_moves = info["available_moves"]

              if episode % 2 == 0:
                  start_time = current_time()
                  action = dqn_agent.step(observation, available_moves)
                  decision_time = current_time() - start_time
                  dqn_agent.update_epsilon(episode, EPSILON_DECAY_FRAMES)
              else:
                  start_time = current_time()
                  action = llm_agent.step(observation, info)
                  decision_time = current_time() - start_time

              next_observation, reward, terminal, truncated, info = env.step(action)


              total_rewards += reward
              #total_damage_dealt += info.get("damage_dealt", 0)
              total_decision_time += decision_time
              if reward > 0:
                  win_count += 1
              if not terminal:
                  survival_count += 1

              if episode % TARGET_UPDATE_FREQ == 0:
                  target_model.load_state_dict(model.state_dict())

              if terminal or truncated:
                  break

              observations.append(observation)
              actions.append(action)
              rewards.append(reward)
              next_observations.append(next_observation)
              terminals.append(terminal)

              observation = next_observation

        buffer.push(observations, actions, rewards, next_observations, terminals)

        train_dqn(model, target_model, buffer, optimizer)

        metrics["Episode"].append(episode)
        metrics["Win/Loss Ratio"].append(win_count / episode)
        #metrics["Average Damage Dealt"].append(total_damage_dealt / episode)
        metrics["Total Rewards"].append(total_rewards)
        metrics["Survival Rate"].append(survival_count / episode)
        metrics["Time to Decision"].append(total_decision_time / episode)
        metrics["Performance Improvement Rate"].append(total_rewards / episode)
        #metrics["Efficiency Score"].append((win_count / episode) + (total_damage_dealt / episode) - (total_decision_time / episode))

    df_metrics = pd.DataFrame(metrics)
    print(df_metrics)
    df_metrics.to_excel(f"{output_folder}/metrics_plot.xlsx", index=False)

    df_metrics.plot(x="Episode", y=["Win/Loss Ratio",   "Survival Rate", "Time to Decision", "Performance Improvement Rate", "Total Rewards"], subplots=True, layout=(3, 2), figsize=(12, 10))
    plt.savefig(f"{output_folder}/metrics_plot.png")
    plt.show()
    # wait for user input before closing
    input("Press Enter to close...")
    plt.close()

if __name__ == "__main__":
    main()
