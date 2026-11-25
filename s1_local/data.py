"""Dataset loading for the local JEV distillation model.

Reads the clean training records produced by
``scripts/export_choice_training_data.py`` (one JSON object per line with
``state``, ``options``, ``chosen_index`` and ``probability_vector``) and turns
them into padded token tensors with soft (teacher probabilities) and hard
(chosen index) targets.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import torch
from torch.utils.data import Dataset

from .tokenizer import S1Tokenizer


def load_records(paths: Sequence[str], max_options: int = 64) -> List[dict]:
    """Load and validate training records from JSONL files."""
    records: List[dict] = []
    for path in paths:
        for line_no, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            state = rec.get('state')
            options = rec.get('options')
            chosen = rec.get('chosen_index')
            if not isinstance(state, str) or not state.strip():
                continue
            if not isinstance(options, list) or not options:
                continue
            if isinstance(chosen, bool) or not isinstance(chosen, int):
                continue
            if not 0 <= chosen < len(options) or len(options) > max_options:
                continue
            vec = rec.get('probability_vector')
            if not isinstance(vec, list) or len(vec) != len(options) or sum(vec) <= 0:
                vec = None
            records.append({
                'state': state,
                'options': [str(o) for o in options],
                'chosen_index': chosen,
                'probability_vector': vec,
                'entity': rec.get('entity'),
            })
    return records


def split_records(records: List[dict], val_fraction: float = 0.1,
                  seed: int = 7) -> Tuple[List[dict], List[dict]]:
    """Group-aware train/val split.

    Two safeguards against an inflated validation score:

    1. **Exact dedup** — identical ``(state, options)`` records (the same
       decision logged across repeated sim runs) collapse to one example.
    2. **Entity-level grouping** — examples are grouped by the acting
       entity, so all battles involving an entity land entirely on one
       side of the split. A validation example never shares a state, an
       option menu, or the acting entity with a training example.

    Falls back to grouping by state hash when a record has no ``entity``
    field. Returns deduplicated records on both sides.
    """
    seen = set()
    groups: Dict[str, List[dict]] = {}
    for rec in records:
        key = (rec['state'], tuple(rec['options']))
        if key in seen:
            continue
        seen.add(key)
        gid = rec.get('entity') or f"state:{hash(rec['state']) & 0xffffff:x}"
        groups.setdefault(gid, []).append(rec)

    total = sum(len(g) for g in groups.values())
    n_target_val = max(1, int(total * val_fraction))
    gids = list(groups)
    random.Random(seed).shuffle(gids)
    val_ids, n_val = set(), 0
    for gid in gids:
        if n_val >= n_target_val:
            break
        val_ids.add(gid)
        n_val += len(groups[gid])
    train = [r for gid, g in groups.items() if gid not in val_ids for r in g]
    val = [r for gid in val_ids for r in groups[gid]]
    return train, val


def fit_tokenizer(records: List[dict], max_vocab: int = 30000, min_freq: int = 2) -> S1Tokenizer:
    texts: Iterable[str] = []
    for rec in records:
        texts.append(rec['state'])
        texts.extend(rec['options'])
    return S1Tokenizer.build(texts, max_vocab=max_vocab, min_freq=min_freq)


class S1ChoiceDataset(Dataset):
    """Tokenized choice examples with soft + hard targets."""

    def __init__(self, records: List[dict], tokenizer: S1Tokenizer,
                 max_state_len: int, max_option_len: int):
        self.records = records
        self.tokenizer = tokenizer
        self.max_state_len = max_state_len
        self.max_option_len = max_option_len

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, i: int) -> Dict[str, torch.Tensor]:
        rec = self.records[i]
        tok = self.tokenizer
        state_ids = tok.encode(rec['state'], self.max_state_len)
        raw_opt_ids = [tok.encode(o, self.max_option_len) for o in rec['options']]
        options = rec['options']
        # Pad options to a uniform width inside the sample (collate pads across
        # the batch). Pad id is 0 (tokenizer [PAD]); token_mask marks real tokens.
        width = max(len(ids) for ids in raw_opt_ids)
        opt_ids = [ids + [0] * (width - len(ids)) for ids in raw_opt_ids]
        token_mask = [[1] * len(ids) + [0] * (width - len(ids)) for ids in raw_opt_ids]
        if rec['probability_vector'] is not None:
            probs = list(rec['probability_vector'])
        else:
            probs = [0.0] * len(options)
            probs[rec['chosen_index']] = 1.0
        return {
            'state_ids': torch.tensor(state_ids, dtype=torch.long),
            'option_ids': torch.tensor(opt_ids, dtype=torch.long),
            'option_token_mask': torch.tensor(token_mask, dtype=torch.float32),
            'target': torch.tensor(probs, dtype=torch.float32),
            'hard': torch.tensor(rec['chosen_index'], dtype=torch.long),
        }


def collate(batch: List[Dict[str, torch.Tensor]]) -> Dict[str, torch.Tensor]:
    """Pad to batch max lengths; return masks plus soft/hard targets."""
    pad = batch[0]['state_ids'].new_tensor(0)  # pad id == 0 by tokenizer construction
    b = len(batch)
    ls = max(item['state_ids'].shape[0] for item in batch)
    k = max(item['option_ids'].shape[0] for item in batch)
    lo = max(item['option_ids'].shape[1] for item in batch)

    state_ids = torch.full((b, ls), 0, dtype=torch.long)
    state_mask = torch.zeros((b, ls), dtype=torch.float32)
    option_ids = torch.full((b, k, lo), 0, dtype=torch.long)
    option_token_mask = torch.zeros((b, k, lo), dtype=torch.float32)
    option_mask = torch.zeros((b, k), dtype=torch.float32)
    target = torch.zeros((b, k), dtype=torch.float32)
    hard = torch.zeros(b, dtype=torch.long)

    for i, item in enumerate(batch):
        s = item['state_ids']
        state_ids[i, :s.shape[0]] = s
        state_mask[i, :s.shape[0]] = 1.0
        o = item['option_ids']
        option_ids[i, :o.shape[0], :o.shape[1]] = o
        tm = item['option_token_mask']
        option_token_mask[i, :tm.shape[0], :tm.shape[1]] = tm
        n_opt = o.shape[0]
        option_mask[i, :n_opt] = 1.0
        target[i, :n_opt] = item['target']
        hard[i] = item['hard']

    return {
        'state_ids': state_ids,
        'state_mask': state_mask,
        'option_ids': option_ids,
        'option_mask': option_mask,
        'option_token_mask': option_token_mask,
        'target': target,
        'hard': hard,
    }
