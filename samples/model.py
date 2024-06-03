import torch
import torch.nn as nn
import torch.nn.functional as F

class QNetwork(nn.Module):
    def __init__(self, num_actions=255):
        super(QNetwork, self).__init__()
        
        # CNN layers for the map
        self.conv1 = nn.Conv2d(3, 16, kernel_size=3, stride=1, padding=1)
        self.conv2 = nn.Conv2d(16, 32, kernel_size=3, stride=1, padding=1)
        self.conv3 = nn.Conv2d(32, 64, kernel_size=3, stride=1, padding=1)
        
        # Fully connected layers for scalar inputs, flattened map, and action components
        self.fc1 = nn.Linear(64 * 12 * 12 + 1 + 1 + 3 + 1 + 2 + 2 + 2, 512)
        
        # Embedding for discrete movement and binary action
        self.movement_embedding = nn.Embedding(256, 10)
        self.binary_action_embedding = nn.Embedding(2, 2)  # Embedding for binary action
        
        # Final layer to output the Q-values for each action
        self.out = nn.Linear(512 + 10 + 2, num_actions)

    

    def forward(self, x, action):
        health_enemy, health_pct, map_input, movement, turn_info = \
            x['health_enemy'], x['health_pct'], x['map'], x['movement'], x['turn_info']
        
        map_input = torch.tensor(x['map'], dtype=torch.float32)
        map_input = map_input.permute(2, 0, 1).unsqueeze(0)

        health_enemy = torch.tensor(health_enemy, dtype=torch.float32).unsqueeze(0)
        health_pct = torch.tensor(health_pct, dtype=torch.float32).unsqueeze(0)
        movement = torch.tensor(movement, dtype=torch.long).unsqueeze(0)
        turn_info = torch.tensor(turn_info, dtype=torch.float32).unsqueeze(0)

        action1, action2, action3, action4 = action

        action1 = torch.tensor(action1, dtype=torch.float32).unsqueeze(0)
        action2 = torch.tensor(action2, dtype=torch.float32).unsqueeze(0)
        action3 = torch.tensor(action3, dtype=torch.float32).unsqueeze(0)
        action4 = torch.tensor(action4, dtype=torch.long).unsqueeze(0)
        
        # Normalize map
        map_input = (map_input + 1.0) / 256.0
        

        # Pass map through CNN
        x = F.relu(self.conv1(map_input))
        x = F.relu(self.conv2(x))
        x = F.relu(self.conv3(x))
        x = x.view(x.size(0), -1)  # Flatten
        
        # Concatenate all features
        health_info = torch.cat((health_enemy, health_pct, turn_info), dim=1)
        print(f"action shapes: {action1.shape}, {action2.shape}, {action3.shape}")
        
        action_features = torch.cat((action1, action2, action3), dim=1)
        movement_embed = self.movement_embedding(movement)
        action4_embed = self.binary_action_embedding(action4)
        
        x = torch.cat((x, health_info, movement_embed, action_features, action4_embed), dim=1)
        
        # Fully connected layer
        x = F.relu(self.fc1(x))
        
        # Output layer
        x = self.out(x)
        return x
