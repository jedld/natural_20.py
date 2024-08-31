import torch
import torch.nn as nn
import torch.nn.functional as F
from natural20.gym.llm_helpers.prompting_utils import action_to_prompt
import pdb
import os

class QNetwork(nn.Module):
    def __init__(self, device='cpu', viewport_size = (12, 12)):
        super(QNetwork, self).__init__()

        # CNN layers for the map
        self.conv1 = nn.Conv2d(12, 16, kernel_size=4, stride=1, padding=0)
        self.conv2 = nn.Conv2d(16, 32, kernel_size=4, stride=1, padding=0)
        self.conv3 = nn.Conv2d(32, 64, kernel_size=4, stride=1, padding=0)

        self.width, self.height = viewport_size
        # Fully connected layers for scalar inputs, flattened map, and action components
        self.fc1 = nn.Linear(269, 64)

        # Embedding for discrete movement and binary action
        self.action_type_embedding = nn.Embedding(256, 4)
        self.binary_action_embedding = nn.Embedding(256, 4)  # Embedding for binary action
        self.binary_action_subtype_embedding = nn.Embedding(256, 4)
        self.weapon_type_embedding = nn.Embedding(256, 4)
        self.entity_type_embedding = nn.Embedding(256, 4)
        self.terrain_type_embedding = nn.Embedding(256, 3)
        # Final layer to output the Q-value for the action
        self.fc2 = nn.Linear(64, 32)
        self.fc3 = nn.Linear(32, 16)
        self.out = nn.Linear(16, 1)
        self.device = device

    def convert_batch(self, batch_x, batch_action, device='cpu', pre_converted=False, pre_converted_action=False):
        map_inputs = []
        health_enemys = []
        conditions = []
        enemy_conditions = []
        enemy_reactions = []
        health_pcts = []
        movements = []
        turn_infos = []
        ability_infos = []
        player_types = []
        enemy_types = []
        player_acs = []
        enemy_acs = []
        player_equipeds = []
        is_reactions = []

        for x in batch_x:
            health_enemy, health_pct, condition, enemy_condition, enemy_reaction, map_input, movement, \
                turn_info, ability_info, player_type, enemy_type, player_ac, enemy_ac, player_equiped, \
                is_reaction = \
                x['health_enemy'], x['health_pct'], x['conditions'], x['enemy_conditions'], \
                x['enemy_reactions'], x['map'], x['movement'], \
                x['turn_info'], x['ability_info'], x['player_type'], x['enemy_type'], \
                x['player_ac'], x['enemy_ac'], x['player_equipped'], x['is_reaction']

            if not pre_converted:
                map_input = torch.tensor(map_input, dtype=torch.int).to(device)

            # Extract the entity and terrain channels and flatten them
            map_input_entity = map_input[:, :, 0].view(-1)
            map_input_terrain = map_input[:, :, 1].view(-1)
            # Apply the embeddings
            map_input_entity = self.entity_type_embedding(map_input_entity)
            map_input_terrain = self.terrain_type_embedding(map_input_terrain)
            # Reshape the embedded channels back to the desired dimensions
            map_input_entity = map_input_entity.view(self.width, self.height, -1)
            map_input_terrain = map_input_terrain.view(self.width, self.height, -1)
            # Extract and normalize the leftover channels
            left_over_channels = map_input[:, :, 2:].float() / 255.0
            # Concatenate all channels
            map_input = torch.cat((map_input_entity, map_input_terrain, left_over_channels), dim=2)

            map_inputs.append(map_input)

            if not pre_converted:
                condition = torch.tensor(condition, dtype=torch.float32).to(device)
                enemy_condition = torch.tensor(enemy_condition, dtype=torch.float32).to(device)
                health_enemy = torch.tensor(health_enemy, dtype=torch.float32).to(device)
                health_pct = torch.tensor(health_pct, dtype=torch.float32).to(device)
                enemy_reaction = torch.tensor(enemy_reaction, dtype=torch.float32).to(device)
                movement = torch.tensor(movement / 255.0, dtype=torch.float32).to(device)
                turn_info = torch.tensor(turn_info, dtype=torch.float32).to(device)
                ability_info = torch.tensor(ability_info, dtype=torch.float32).to(device)
                player_type = torch.tensor(player_type[0], dtype=torch.long).to(device)
                enemy_type = torch.tensor(enemy_type[0], dtype=torch.long).to(device)
                player_ac = torch.tensor(player_ac, dtype=torch.float32).to(device)
                enemy_ac = torch.tensor(enemy_ac, dtype=torch.float32).to(device)
                player_equiped = torch.tensor(player_equiped, dtype=torch.long).to(device).unsqueeze(1)
                is_reaction = torch.tensor(is_reaction, dtype=torch.float32).to(device)

            conditions.append(condition)
            enemy_conditions.append(enemy_condition)
            health_enemys.append(health_enemy)
            health_pcts.append(health_pct)
            enemy_reactions.append(enemy_reaction)
            movements.append(movement)
            turn_infos.append(turn_info)
            ability_infos.append(ability_info)
            player_types.append(player_type)
            enemy_types.append(enemy_type)
            player_acs.append(player_ac)
            enemy_acs.append(enemy_ac)
            is_reactions.append(is_reaction)

            equiped_flattened = self.weapon_type_embedding(player_equiped).view(-1)
            player_equipeds.append(equiped_flattened)

        action1s = []
        action2s = []
        action3s = []
        action4s = []
        action5s = []

        for action in batch_action:
            action1, action2, action3, action4, action5 = action
            if not pre_converted_action:
                action1 = torch.tensor(action1, dtype=torch.long).to(device)
                action2 = torch.tensor(action2, dtype=torch.float32).to(device)
                action3 = torch.tensor(action3, dtype=torch.float32).to(device)
                action4 = torch.tensor(action4, dtype=torch.long).to(device)
                action5 = torch.tensor(action5, dtype=torch.long).to(device)

            action1s.append(action1)
            action2s.append(action2)
            action3s.append(action3)
            action4s.append(action4)
            action5s.append(action5)

        return torch.stack(map_inputs).to(device), \
               torch.stack(player_types).to(device), \
               torch.stack(enemy_types).to(device), \
               torch.stack(player_acs).to(device), \
               torch.stack(player_equipeds).to(device), \
               torch.stack(conditions).to(device), torch.stack(enemy_conditions).to(device), \
               torch.stack(health_enemys).to(device), torch.stack(health_pcts).to(device), \
               torch.stack(enemy_reactions).to(device), torch.stack(ability_infos).to(device),\
               torch.stack(is_reactions).to(device), \
               torch.stack(movements).to(device), \
               torch.stack(turn_infos).to(device), \
               torch.stack(action1s).to(device), \
               torch.stack(action2s).to(device), torch.stack(action3s).to(device), torch.stack(action4s).to(device), \
               torch.stack(action5s).to(device)

    def forward(self, x, action, pre_converted=False, pre_converted_action=False):
        if isinstance(x, dict):
            map_input, player_type, enemy_type, player_ac, equiped, condition, condition_enemy, \
                health_enemy, health_pct, enemy_reaction, is_reaction, ability_info, movement, turn_info, \
                action1, action2, action3, action4, action5 = self.convert_batch([x], [action], self.device, pre_converted=pre_converted, pre_converted_action=pre_converted_action)
        else:
            map_input, player_type, enemy_type, player_ac, equiped, condition, condition_enemy, \
                health_enemy, health_pct, enemy_reaction, is_reaction, ability_info, movement, turn_info, \
                action1, action2, action3, action4, action5 = self.convert_batch(x, action, self.device, pre_converted=pre_converted, pre_converted_action=pre_converted_action)

        # Pass map through CNN
        x = F.relu(self.conv1(map_input))
        x = F.relu(self.conv2(x))
        x = F.relu(self.conv3(x))
        x = x.view(x.size(0), -1)  # Flatten

        # Concatenate all features
        health_info = torch.cat((health_enemy, health_pct, turn_info, player_ac, movement), dim=1)
        action_features = torch.cat((action2, action3), dim=1)
        action_embed = self.action_type_embedding(action1 + 1)
        action4_embed = self.binary_action_embedding(action4)
        action5_embed = self.binary_action_subtype_embedding(action5)
        player_type_embeds = self.entity_type_embedding(player_type)
        enemy_type_embeds = self.entity_type_embedding(enemy_type)

        # normalize ability info
        ability_info = ability_info / 256.0
        x = torch.cat((x, equiped, is_reaction, condition, condition_enemy, health_info, enemy_reaction, action_embed, action_features, action4_embed, action5_embed, player_type_embeds, enemy_type_embeds, ability_info), dim=1)

        # Fully connected layer
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = F.relu(self.fc3(x))

        # Output layer
        x = self.out(x)
        return x


class ModelPolicy:
    def __init__(self, session, model_path, device, debug=False):
        self.session = session
        self.weapon_mappings, self.spell_mappings, self.entity_mappings = embedding_loader(self.session)
        if self.weapon_mappings is None or self.spell_mappings is None:
            raise ValueError("Embeddings not loaded")
        self.debug = debug
        self.model = QNetwork(device=device)
        self.model.to(device)
        fname = model_path
        if not os.path.exists(fname):
            raise FileNotFoundError(f"Model file {fname} not found. Please run dnd_dqn.ipynb notebook to train an agent.")
        self.model.load_state_dict(torch.load(fname))

    def action(self, state, info):
        available_moves = info["available_moves"]
        values = torch.stack([self.model(state, move) for move in available_moves])
        if self.debug:
            for index, v in enumerate(values):
                description = action_to_prompt(available_moves[index], self.weapon_mappings, self.spell_mappings)
                print(f"{index}: {description} {v.item()}")

        chosen_index = torch.argmax(values).item()
        if self.debug:
            print(f"Chosen index: {chosen_index}")
        return available_moves[chosen_index]