"""Load a trained checkpoint and answer choice questions from raw text.

Used by ``scripts/s1_local_api_server.py`` (the TypeSafe-compatible wire
server) and by any local caller that wants ``decide_action``-style answers
without the network.
"""
from __future__ import annotations

import io
import json
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import torch

from .data import collate
from .model import S1Config, S1SystemOne
from .tokenizer import S1Tokenizer


class _RenamedUnpickler(pickle.Unpickler):
    """Unpickler for checkpoints pickled before the jev_local -> s1_local rename."""

    def find_class(self, module, name):
        if module.startswith('jev_local'):
            module = 's1_local' + module[len('jev_local'):]
            name = name.replace('JevTokenizer', 'S1Tokenizer')
        return super().find_class(module, name)


class S1LocalPredictor:
    """Checkpoint + tokenizer wrapper producing wire-shaped answers."""

    def __init__(self, model: S1SystemOne, tokenizer: S1Tokenizer,
                 config: S1Config, max_options: Optional[int] = None,
                 device: Optional[str] = None):
        self.model = model.eval()
        self.tokenizer = tokenizer
        self.config = config
        self.max_options = max_options or config.max_options
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.meta: Dict[str, Any] = {}
        self.model.to(self.device)

    @classmethod
    def load(cls, checkpoint_path: str, device: Optional[str] = None) -> "S1LocalPredictor":
        path = Path(checkpoint_path)
        blob = torch.load(path, map_location='cpu', weights_only=False)
        config = S1Config.from_dict(blob['config'])
        try:
            obj = pickle.loads(blob['tokenizer_pickle'])
        except ModuleNotFoundError:
            obj = _RenamedUnpickler(io.BytesIO(blob['tokenizer_pickle'])).load()
        tokenizer = obj if isinstance(obj, S1Tokenizer) else S1Tokenizer(obj)
        model = S1SystemOne(config)
        model.load_state_dict(blob['model_state'])
        dev = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        model.to(dev)
        predictor = cls(model, tokenizer, config, max_options=blob.get('max_options'), device=dev)
        predictor.meta = {k: blob.get(k) for k in ('train_metrics', 'val_metrics', 'trained_at', 'model_name')}
        return predictor

    def _tokenize(self, state: str, options: Sequence[str]) -> Dict[str, torch.Tensor]:
        tok = self.tokenizer
        raw = [tok.encode(o, self.config.max_option_len) for o in options]
        width = max(len(ids) for ids in raw)
        opt_ids = [ids + [0] * (width - len(ids)) for ids in raw]
        token_mask = [[1] * len(ids) + [0] * (width - len(ids)) for ids in raw]
        item = {
            'state_ids': torch.tensor(tok.encode(state, self.config.max_state_len), dtype=torch.long),
            'option_ids': torch.tensor(opt_ids, dtype=torch.long),
            'option_token_mask': torch.tensor(token_mask, dtype=torch.float32),
            'target': torch.tensor([1.0 / len(options)] * len(options), dtype=torch.float32),
            'hard': torch.tensor(0, dtype=torch.long),
        }
        batch = collate([item])
        return {k: v.to(self.device) for k, v in batch.items()}

    @torch.no_grad()
    def decide(self, state: str, options: Sequence[str], temperature: float = 1.0) -> Dict[str, Any]:
        """Return ``{index, choice, confidence, probabilities}`` like JevProvider."""
        if not options:
            return {'index': 0, 'choice': '0', 'confidence': 0.0, 'probabilities': {'0': 1.0}}
        if len(options) > self.max_options:
            raise ValueError(f"{len(options)} options exceed local model cap ({self.max_options})")
        batch = self._tokenize(state, options)
        logits = self.model(batch['state_ids'], batch['state_mask'],
                            batch['option_ids'], batch['option_mask'],
                            batch['option_token_mask'])
        logits = logits[0, :len(options)]
        if temperature and temperature != 1.0:
            logits = logits / max(1e-6, temperature)
        probs = torch.softmax(logits, dim=-1).tolist()
        probs = [max(0.0, float(p)) for p in probs]
        total = sum(probs) or 1.0
        probs = [p / total for p in probs]
        best = max(range(len(probs)), key=lambda i: probs[i])
        return {
            'index': best,
            'choice': str(best),
            'confidence': probs[best],
            'probabilities': {str(i): probs[i] for i in range(len(probs))},
        }

    @torch.no_grad()
    def decide_noul(self, state: str, instructions: str) -> Dict[str, Any]:
        """Yes/no fallback head: no noul training rows exist in the distillation
        logs, so the choice model is asked to weigh the two verbalized answers."""
        answer = self.decide(state, [f"{instructions}\nAnswer: yes.",
                                     f"{instructions}\nAnswer: no."])
        probs = answer['probabilities']
        noul = probs.get('0', 0.5)
        return {'noul': noul, 'confidence': max(noul, 1.0 - noul)}

    # ------------------------------------------------------------------ #
    # Wire protocol helpers (typesafe_sdk /v1/systemone)                 #
    # ------------------------------------------------------------------ #
    def answer_questions(self, state: Any, questions: Dict[str, dict],
                         temperature: float = 1.0) -> Dict[str, dict]:
        """Answer a mapping of question-name -> question dict, returning the
        wire-format answer objects consumed by typesafe_sdk and JevProvider.
        """
        state_text = state if isinstance(state, str) else json.dumps(state, ensure_ascii=False)
        answers: Dict[str, dict] = {}
        for name, q in (questions or {}).items():
            qtype = q.get('type')
            instructions = q.get('instructions') or ''
            if qtype == 'choice':
                criteria = q.get('criteria') or {}
                labels = list(criteria.keys())
                options = [criteria.get(label) if isinstance(criteria.get(label), str)
                           else f"{label}: {json.dumps(criteria.get(label), ensure_ascii=False)}"
                           if criteria.get(label) is not None else str(label)
                           for label in labels]
                if not labels:
                    answers[name] = {'type': 'choice', 'choice': '', 'confidence': 0.0,
                                     'probabilities': {}}
                    continue
                verdict = self.decide(f"{instructions}\n\n{state_text}" if instructions else state_text,
                                      options, temperature=temperature)
                answers[name] = {
                    'type': 'choice',
                    'choice': labels[verdict['index']],
                    'confidence': round(verdict['confidence'], 6),
                    'probabilities': {labels[int(i)]: round(p, 6)
                                      for i, p in verdict['probabilities'].items()},
                }
            elif qtype == 'noul':
                verdict = self.decide_noul(state_text, instructions)
                answers[name] = {'type': 'noul', 'noul': round(verdict['noul'], 6)}
            elif qtype == 'score':
                levels = q.get('criteria') or []
                if not levels:
                    answers[name] = {'type': 'score', 'score': 0.0, 'confidence': 0.0,
                                     'legend': {}, 'probabilities': {}}
                    continue
                options = [f"score level {i}: {json.dumps(level, ensure_ascii=False)}"
                           for i, level in enumerate(levels)]
                verdict = self.decide(f"{instructions}\n\n{state_text}" if instructions else state_text,
                                      options, temperature=temperature)
                probs = {int(k): v for k, v in verdict['probabilities'].items()}
                expected = sum(i * p for i, p in probs.items())
                answers[name] = {
                    'type': 'score',
                    'score': round(expected, 6),
                    'confidence': round(max(probs.values()) if probs else 0.0, 6),
                    'legend': {str(i): json.dumps(level, ensure_ascii=False)
                               for i, level in enumerate(levels)},
                    'probabilities': {str(i): round(p, 6) for i, p in probs.items()},
                }
            else:
                raise ValueError(f"Unsupported question type: {qtype!r}")
        return answers
