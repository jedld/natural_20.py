import collections
import torch
import numpy as np
import sys

class ReplayBuffer:
    def __init__(self, capacity, device):
        self.buffer = collections.deque(maxlen=capacity)
        self.device = device
 
    def push(self, states, actions, rewards, infos, is_terminal):
        converted_states = []
        converted_actions = []
        for x in states:
            health_enemy, health_pct, condition, enemy_condition, enemy_reaction, map_input, movement, \
                    turn_info, ability_info, player_type, enemy_type, player_ac, enemy_ac, player_equipped, \
                    is_reaction = \
                    x['health_enemy'], x['health_pct'], x['conditions'], x['enemy_conditions'], \
                    x['enemy_reactions'], x['map'], x['movement'], \
                    x['turn_info'], x['ability_info'], x['player_type'], x['enemy_type'], \
                    x['player_ac'], x['enemy_ac'], x['player_equipped'], x['is_reaction']
            state = {}
            state['map'] = torch.tensor(map_input, dtype=torch.int).to(self.device)
            state['conditions'] = torch.tensor(condition, dtype=torch.float32)
            state['enemy_conditions'] = torch.tensor(enemy_condition, dtype=torch.float32)
            state['health_enemy'] = torch.tensor(health_enemy, dtype=torch.float32)
            state['health_pct'] = torch.tensor(health_pct, dtype=torch.float32)
            state['enemy_reactions'] = torch.tensor(enemy_reaction, dtype=torch.float32)
            state['movement'] = torch.tensor(movement / 255.0, dtype=torch.float32)
            state['turn_info'] = torch.tensor(turn_info, dtype=torch.float32)
            state['ability_info'] = torch.tensor(ability_info, dtype=torch.float32)
            state['player_type'] = torch.tensor(player_type[0], dtype=torch.long)
            state['enemy_type'] = torch.tensor(enemy_type[0], dtype=torch.long)
            state['player_ac'] = torch.tensor(player_ac, dtype=torch.float32)
            state['enemy_ac'] = torch.tensor(enemy_ac, dtype=torch.float32)
            state['is_reaction'] = torch.tensor(is_reaction, dtype=torch.float32)
            state['player_equipped'] = torch.tensor(player_equipped, dtype=torch.long).to(self.device).unsqueeze(1)
            converted_states.append(state)

        for a in actions:
            action1, action2, action3, action4, action5 = a
            converted_actions.append((torch.tensor(action1, dtype=torch.long),
                                        torch.tensor(action2, dtype=torch.float32),
                                        torch.tensor(action3, dtype=torch.float32),
                                        torch.tensor(action4, dtype=torch.long),
                                        torch.tensor(action5, dtype=torch.long)))

        self.buffer.append((converted_states, converted_actions, rewards, infos, is_terminal))

    def sample(self, batch_size):
        indices = np.random.choice(len(self.buffer), batch_size)
        states, actions, rewards, infos, is_terminals = zip(*[self.buffer[idx] for idx in indices])
        return states, actions, rewards, infos, is_terminals

    def __len__(self):
        return len(self.buffer)
    
    def print_stats(self):
        print(f"Buffer size: {len(self.buffer)}")
        print(f"Memory usage: {self.memory_usage()} bytes")
    
    # memory usage of the buffer in bytes
    def memory_usage(self):
        total_size = 0
        for item in self.buffer:
            states, actions, rewards, infos, is_terminals = item
            for s in states:
                total_size += sys.getsizeof(s)
            total_size += sys.getsizeof(actions)
            total_size += sys.getsizeof(rewards)
            total_size += sys.getsizeof(infos)
            total_size += sys.getsizeof(is_terminals)

        return total_size