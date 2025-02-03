from natural20.session import Session
from natural20.gym.dndenv import dndenv, action_type_to_int
from gymnasium import register, envs, make
from natural20.gym.llm_helpers.prompting_utils import action_to_prompt
from natural20.gym.dndenv import embedding_loader
from natural20.event_manager import EventManager
from natural20.gym.dqn.policy import ModelPolicy
from natural20.gym.dqn.replay_buffer import ReplayBuffer
import gc
import torch
import random
import numpy as np
import os
import tqdm
import collections
from natural20.gym.dqn.model import QNetwork
import torch.optim as optim
import torch.nn as nn
from torch.utils.tensorboard import SummaryWriter
import argparse

# Global constants and hyperparameters
WEIGHTS_FOLDER = "model_weights_all"
TRAJECTORY_POLICY = "e-greedy"
NUM_UPDATES = 2  # number of training steps to update the Q-network
TEMP_DECAY = 0.90
BUFFER_CAPACITY = 3000
FRAMES_TO_STORE = 2
MAX_STEPS = 3000
BATCH_SIZE = 64
TARGET_UPDATE_FREQ = 1  # how often to update the target network
T_HORIZON = 512
EPSILON_START = 1.0
EPSILON_FINAL = 0.01
EPSILON_DECAY_FRAMES = 10**3
EVAL_STEPS = 30

# Where to save best models and checkpoints
PROJECT_OUTPUT_PATH = "model_weights_std"
if not os.path.exists(PROJECT_OUTPUT_PATH):
    os.mkdir(PROJECT_OUTPUT_PATH)

# Agent classes remain unchanged.
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

    def __str__(self) -> str:
        return "Model Agent"

event_manager = EventManager()
event_manager.standard_cli()
session = Session(root_path="map_with_obstacles", event_manager=event_manager)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Add command-line arguments for weights and checkpointing.
parser = argparse.ArgumentParser(description='Train a DQN agent for the DnD environment.')
parser.add_argument('--weights', type=str, default=None, help='Path to the weights file to load')
parser.add_argument('--checkpoint', type=str, default=None, help='Path to a checkpoint file to resume training')
args = parser.parse_args()

model_policy = ModelPolicy(session, weights_file=args.weights, device=device)
adversary_agent = ModelAgent(model_policy)

def act_with_policy(state, info, model, policy='e-greedy', temperature=5.0, epsilon=0.1):
    available_moves = info["available_moves"]
    with torch.no_grad():
        if policy == 'boltzmann':
            values = torch.stack([model(state, move).squeeze() for move in available_moves])
            if len(values) > 1:
                if temperature != 0:
                    values = values / temperature
                else:
                    raise ValueError("Temperature is zero, which can lead to division by zero.")
                # Stabilize the exponential calculation
                values = values - torch.max(values)
                values = torch.exp(values)
                sum_values = torch.sum(values)
                if sum_values > 0:
                    values = values / sum_values
                    chosen_index = torch.multinomial(values, 1).item()
                else:
                    print("Sum of exponentiated values is zero. Adjust the model or input.")
                    chosen_index = torch.randint(len(available_moves), (1,)).item()
            else:
                chosen_index = 0
        elif policy == 'e-greedy':
            if random.random() < epsilon:
                move_types = collections.defaultdict(list)
                for orig_index, move in enumerate(available_moves):
                    move_types[move[0]].append(orig_index)
                chosen_move_type = random.choice(list(move_types.keys()))
                chosen_index = random.choice(move_types[chosen_move_type])
            else:
                values = torch.stack([model(state, move) for move in available_moves])
                chosen_index = torch.argmax(values).item()
        elif policy == 'greedy':
            values = torch.stack([model(state, move) for move in available_moves])
            chosen_index = torch.argmax(values).item()
        else:
            raise ValueError(f"Unknown policy: {policy}")
    
    return available_moves[chosen_index]

def generate_trajectory(env, model, policy='e-greedy', temperature=5.0, epsilon=0.1, horizon=500, quick_exit=False):
    states = []
    actions = []
    rewards = []
    dones = []
    truncateds = []
    infos = []

    def reaction_callback(state, reward, done, truncated, info):
        action = act_with_policy(state, info, model, policy, temperature, epsilon)
        states.append(state)
        actions.append(action)
        rewards.append(reward)
        dones.append(done)
        truncateds.append(truncated)
        infos.append(info)
        return action

    state, info = env.reset(reaction_callback=reaction_callback)

    for _ in range(horizon):
        action = act_with_policy(state, info, model, policy, temperature, epsilon)
        next_state, reward, done, truncated, next_info = env.step(action)
        states.append(state)
        actions.append(action)
        rewards.append(reward)
        dones.append(done)
        truncateds.append(truncated)
        infos.append(info)
        if done or truncated:
            break    
        state = next_state
        info = next_info
        
    states.append(next_state)
    infos.append(next_info)
    actions.append((-1, (0, 0), (0, 0), 0, 0))
    return states, actions, rewards, dones, truncateds, infos

def generate_batch_trajectories(env, model, n_rollout, replay_buffer: ReplayBuffer, temperature=5.0, epsilon=0.1, horizon=30, policy='e-greedy'):
    for _ in range(n_rollout):
        state, action, reward, done, truncated, info = generate_trajectory(env, model, temperature=temperature, epsilon=epsilon,
                                                                           horizon=horizon, policy=policy)
        replay_buffer.push(state, action, reward, info, done)

# Initialize a model instance.
model = QNetwork(device=device)
model.to(device)

def train(env, gamma, learning_rate, max_steps=MAX_STEPS, use_td_target=True,
          trajectory_policy='e-greedy',
          label="dnd_egreedy",
          eval_env=None,
          reward_per_episode=None,
          n_rollout=8,
          seed=1337,
          checkpoint_path=None):
    print(f"Training with gamma {gamma} and learning rate {learning_rate}")
    env.seed(seed)

    replay_buffer = ReplayBuffer(BUFFER_CAPACITY, device)
    model = QNetwork(device).to(device)
    target_model = QNetwork(device).to(device)
    target_model.load_state_dict(model.state_dict())
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)

    best_avg = -10
    best_step = 0
    temperature = 5.0
    if reward_per_episode is None:
        reward_per_episode = []
    epsilon = EPSILON_START
    start_step = 0
    current_avg_reward = None  # To show in the progress bar

    # If a checkpoint exists, load it.
    if checkpoint_path is not None and os.path.exists(checkpoint_path):
        print(f"Loading checkpoint from {checkpoint_path}")
        checkpoint = torch.load(checkpoint_path, map_location=device)
        model.load_state_dict(checkpoint['model_state_dict'])
        target_model.load_state_dict(checkpoint['target_model_state_dict'])
        optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        start_step = checkpoint['step']
        epsilon = checkpoint['epsilon']
        temperature = checkpoint['temperature']
        best_avg = checkpoint.get('best_avg', best_avg)
        best_step = checkpoint.get('best_step', best_step)
        replay_buffer = checkpoint.get('replay_buffer', replay_buffer)

    writer = SummaryWriter(log_dir=f"runs/{label}")
    CHECKPOINT_FREQ = 100

    def save_checkpoint(path, current_step):
        checkpoint_data = {
            'step': current_step,
            'model_state_dict': model.state_dict(),
            'target_model_state_dict': target_model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'epsilon': epsilon,
            'temperature': temperature,
            'best_avg': best_avg,
            'best_step': best_step,
            'replay_buffer': replay_buffer,
        }
        torch.save(checkpoint_data, path)
        print(f"Checkpoint saved to {path}")

    # Use tqdm to show progress and update dynamic training metrics.
    with tqdm.tqdm(range(start_step, max_steps), desc="Training", unit="step") as pbar:
        for step in pbar:
            generate_batch_trajectories(env, model, n_rollout, replay_buffer, temperature=temperature,
                                        epsilon=epsilon, policy=trajectory_policy, horizon=T_HORIZON)

            states, actions, rewards, infos, is_terminals = replay_buffer.sample(BATCH_SIZE)
            rewards_collected = 0
            total_loss = 0.0

            for _ in range(NUM_UPDATES):
                rewards_collected = 0
                for i in range(len(states)):
                    s = states[i]
                    a = actions[i]
                    env_info = infos[i]
                    r = torch.tensor(rewards[i]).to(device).unsqueeze(1)
                    is_terminal = torch.tensor(is_terminals[i]).float().to(device).unsqueeze(1)

                    if use_td_target:
                        with torch.no_grad():
                            s_next = s[1:]
                            a_next = a[1:]
                            q_targets = target_model.forward(s_next, a_next, pre_converted=True, pre_converted_action=True).detach()
                    else:
                        with torch.no_grad():
                            s_next = s[1:]
                            s_info = env_info[1:]
                            q_targets = torch.zeros(len(s_next)).to(device)
                            for index in range(len(s_info)):
                                info = s_info[index]
                                state_val = s_next[index]
                                if len(state_val) == 0:
                                    q_targets[index] = 0
                                    continue
                                total_available_moves = len(info["available_moves"])
                                states_t = [state_val] * total_available_moves
                                avail_actions = info["available_moves"]
                                q_values = target_model.forward(states_t, avail_actions, pre_converted=True).detach().squeeze(1)
                                if len(q_values) == 0:
                                    q_targets[index] = 0
                                else:
                                    q_targets[index] = torch.max(q_values).item()
                            q_targets = q_targets.unsqueeze(1)
                            assert q_targets.shape == r.shape, f"q_targets shape {q_targets.shape} != r shape {r.shape}"

                    targets = r + gamma * q_targets * (1 - is_terminal)
                    s_input = s[0:-1]
                    a_input = a[0:-1]
                    output = model.forward(s_input, a_input, pre_converted=True, pre_converted_action=True)
                    q_sa = output

                    value_loss = nn.MSELoss()(q_sa, targets)
                    optimizer.zero_grad()
                    value_loss.backward()
                    total_loss += value_loss.item()
                    rewards_collected += r.sum().item()
                    optimizer.step()

            writer.add_scalar('Loss/Value Loss', total_loss, step)
            writer.add_scalar('Rewards/Collected', rewards_collected, step)

            # Evaluate performance every 10 steps.
            if step % 10 == 0:
                if eval_env is None:
                    eval_env = env

                eval_rewards = []
                for _ in range(EVAL_STEPS):
                    _, _, rewards_eval, _, _, _ = generate_trajectory(eval_env, model, policy='greedy')
                    total_reward = sum(rewards_eval)
                    eval_rewards.append(total_reward)

                avg_rewards = np.mean(eval_rewards)
                std_rewards = np.std(reward_per_episode) if reward_per_episode else 0
                reward_per_episode.append(avg_rewards)
                current_avg_reward = avg_rewards

                writer.add_scalar('Rewards/Average', avg_rewards, step)
                writer.add_scalar('Rewards/Standard Deviation', std_rewards, step)
                writer.add_scalar('Epsilon', epsilon, step)
                writer.add_scalar('Temperature', temperature, step)

                if trajectory_policy == "e-greedy":
                    print(f"{step}: avg rewards {avg_rewards} std: {std_rewards} best avg {best_avg}@{best_step} epsilon {epsilon}")
                elif trajectory_policy == "boltzmann":
                    print(f"{step}: avg rewards {avg_rewards} std: {std_rewards} best avg {best_avg}@{best_step} temperature {temperature}")
                else:
                    print(f"{step}: avg rewards {avg_rewards} std: {std_rewards} best avg {best_avg}@{best_step}")

                replay_buffer.print_stats()

                adversary_rewards = []
                for _ in range(EVAL_STEPS):
                    _, _, rewards_adv, _, _, _ = generate_trajectory(env, model, policy='greedy')
                    total_reward = sum(rewards_adv)
                    adversary_rewards.append(total_reward)

                adv_rewards = np.mean(adversary_rewards)
                writer.add_scalar('Rewards/Adversary', adv_rewards, step)
                print(f"Adversary rewards: {adv_rewards}")
                if adv_rewards > 0:
                    print("Current weights better, updating weights now")
                    model_policy.update_weights(model.state_dict())

                if avg_rewards > best_avg:
                    print(f"New best avg rewards: {avg_rewards} at step {step}")
                    best_avg = avg_rewards
                    best_step = step
                    torch.save(model.state_dict(), f"{PROJECT_OUTPUT_PATH}/model_best_{label}@{step}.pt")
                    torch.save(model.state_dict(), f"{PROJECT_OUTPUT_PATH}/model_best_{label}.pt")

            gc.collect()

            # Decay temperature and epsilon.
            temperature = np.max([0.1, temperature * TEMP_DECAY])
            epsilon = EPSILON_FINAL + (EPSILON_START - EPSILON_FINAL) * np.exp(-1.0 * step / EPSILON_DECAY_FRAMES)

            if step % TARGET_UPDATE_FREQ == 0:
                target_model.load_state_dict(model.state_dict())

            # Save a checkpoint every CHECKPOINT_FREQ steps.
            if (step + 1) % CHECKPOINT_FREQ == 0:
                checkpoint_file = os.path.join(PROJECT_OUTPUT_PATH, f"checkpoint_{label}_step_{step}.pt")
                save_checkpoint(checkpoint_file, step)

            # Update tqdm progress bar with dynamic information.
            pbar.set_postfix({
                'epsilon': f"{epsilon:.3f}",
                'temp': f"{temperature:.3f}",
                'avg_reward': f"{current_avg_reward:.2f}" if current_avg_reward is not None else "N/A"
            })

    writer.close()
    env.close()
    return reward_per_episode

def make_env(root_path, render_mode="ansi", show_logs=True, custom_agent=None):
    return make("dndenv-v0", root_path=root_path,
                render_mode=render_mode,
                damage_based_reward=True,
                custom_agent=custom_agent,
                profiles=lambda: random.choice(['high_elf_fighter', 'high_elf_mage', 'dwarf_cleric', 'halfling_rogue']),
                enemies=lambda: random.choice(['high_elf_fighter', 'high_elf_mage', 'dwarf_cleric', 'halfling_rogue']),
                map_file=lambda: random.choice(['maps/simple_map',
                                                'maps/complex_map',
                                                'maps/game_map',
                                                'maps/walled_map']))

game_setup_path = "map_with_obstacles"

from natural20.generic_controller import GenericController
from natural20.gym.dndenv_controller import DndenvController

env = make_env(game_setup_path, custom_agent=adversary_agent)
eval_env = make_env(game_setup_path)

seed = 1337
# Create a grid of learning rates and gammas.
learning_rates = [0.0001]
gammas = [0.99]

results = {}
for lr in learning_rates:
    results[lr] = {}
    for gamma in gammas:
        seed += 1
        reward_per_episode = train(env, gamma, lr, max_steps=MAX_STEPS, seed=seed,
                                     use_td_target=True, eval_env=eval_env,
                                     checkpoint_path=args.checkpoint)
        results[lr][gamma] = reward_per_episode
