import torch
import torch.nn as nn
import torch.nn.functional as F

class QNetwork(nn.Module):
    def __init__(self, device='cpu', viewport_size = (12, 12)):
        super(QNetwork, self).__init__()
        
        # CNN layers for the map
        self.conv1 = nn.Conv2d(4, 16, kernel_size=3, stride=1, padding=1)
        self.conv2 = nn.Conv2d(16, 32, kernel_size=3, stride=1, padding=1)
        self.conv3 = nn.Conv2d(32, 64, kernel_size=3, stride=1, padding=1)
        
        width, height = viewport_size
        # Fully connected layers for scalar inputs, flattened map, and action components
        self.fc1 = nn.Linear(64 * width * height + 32, 64)
        
        # Embedding for discrete movement and binary action
        self.action_type_embedding = nn.Embedding(256, 4)
        self.movement_embedding = nn.Embedding(256, 2)
        self.binary_action_embedding = nn.Embedding(256, 4)  # Embedding for binary action
        self.binary_action_subtype_embedding = nn.Embedding(256, 4)
        # Final layer to output the Q-value for the action
        self.fc2 = nn.Linear(64, 32)
        self.fc3 = nn.Linear(32, 16)
        self.out = nn.Linear(16, 1)
        self.device = device 

    def convert_batch(self, batch_x, batch_action, device='cpu'):
        map_inputs = []
        health_enemys = []
        enemy_reactions = []
        health_pcts = []
        movements = []
        turn_infos = []
        ability_infos = []
        
        for x in batch_x:
            health_enemy, health_pct, enemy_reaction, map_input, movement, turn_info, ability_info = \
                x['health_enemy'], x['health_pct'], x['enemy_reactions'], x['map'], x['movement'], \
                      x['turn_info'], x['ability_info']
            
            map_input = torch.tensor(x['map'], dtype=torch.float32)
            map_input = map_input.permute(2, 0, 1)
            map_inputs.append(map_input)
            health_enemys.append(torch.tensor(health_enemy, dtype=torch.float32))
            health_pcts.append(torch.tensor(health_pct, dtype=torch.float32))
            enemy_reactions.append(torch.tensor(enemy_reaction, dtype=torch.float32))
            movements.append(torch.tensor(movement, dtype=torch.long))
            turn_infos.append(torch.tensor(turn_info, dtype=torch.float32))
            ability_infos.append(torch.tensor(ability_info, dtype=torch.float32))

        action1s = []
        action2s = []
        action3s = []
        action4s = []
        action5s = []

        for action in batch_action:
            action1, action2, action3, action4, action5 = action
            action1s.append(torch.tensor(action1, dtype=torch.long))
            action2s.append(torch.tensor(action2, dtype=torch.float32))
            action3s.append(torch.tensor(action3, dtype=torch.float32))
            action4s.append(torch.tensor(action4, dtype=torch.long))
            action5s.append(torch.tensor(action5, dtype=torch.long))

            
        return torch.stack(map_inputs).to(device), torch.stack(health_enemys).to(device), torch.stack(health_pcts).to(device), \
               torch.stack(enemy_reactions).to(device), torch.stack(ability_infos).to(device),\
               torch.stack(movements).to(device), torch.stack(turn_infos).to(device), torch.stack(action1s).to(device), \
               torch.stack(action2s).to(device), torch.stack(action3s).to(device), torch.stack(action4s).to(device), \
               torch.stack(action5s).to(device)

    def forward(self, x, action):
        if isinstance(x, dict):
            map_input, health_enemy, health_pct, enemy_reaction, ability_info, movement, turn_info, action1, action2, action3, action4, action5 = self.convert_batch([x], [action], self.device)
        else:
            map_input, health_enemy, health_pct, enemy_reaction, ability_info, movement, turn_info, action1, action2, action3, action4, action5 = self.convert_batch(x, action, self.device)
        
        # Normalize map
        map_input = (map_input + 1.0) / 256.0
        
        # Pass map through CNN
        x = F.relu(self.conv1(map_input))
        x = F.relu(self.conv2(x))
        x = F.relu(self.conv3(x))
        x = x.view(x.size(0), -1)  # Flatten
        
        # Concatenate all features
        health_info = torch.cat((health_enemy, health_pct, turn_info), dim=1)
        action_features = torch.cat((action2, action3), dim=1)
        action_embed = self.action_type_embedding(action1 + 1)
        movement_embed = self.movement_embedding(movement)
        action4_embed = self.binary_action_embedding(action4)
        action5_embed = self.binary_action_subtype_embedding(action5)

        # normalize ability info
        ability_info = ability_info / 256.0

        x = torch.cat((x, health_info, enemy_reaction, action_embed, movement_embed, action_features, action4_embed, action5_embed, ability_info), dim=1)
        
        # Fully connected layer
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))    
        x = F.relu(self.fc3(x))

        # Output layer
        x = self.out(x)
        return x
