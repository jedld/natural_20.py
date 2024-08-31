import os
from model import QNetwork
from natural20.gym.llm_helpers.prompting_utils import action_to_prompt
from natural20.gym.dndenv import embedding_loader
import torch

class ModelPolicy:
    def __init__(self, session, weights_file, device, debug=False):
        self.session = session
        self.weapon_mappings, self.spell_mappings, self.entity_mappings = embedding_loader(self.session)
        if self.weapon_mappings is None or self.spell_mappings is None:
            raise ValueError("Embeddings not loaded")
        self.debug = debug
        self.model = QNetwork(device=device)
        self.model.to(device)
        fname = weights_file
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