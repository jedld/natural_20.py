"""A tiny vocab-from-scratch tokenizer for the local JEV model.

No pretrained tokenizer, no HuggingFace dependency: the vocabulary is built
directly from the training corpus (word tokens + a character fallback for
everything else, so entity names, numbers, and the ASCII POV map always
encode). This mirrors how a "System One" model consumes unstructured state:
the text is just tokens.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, List

PAD = "[PAD]"
UNK = "[UNK]"
CLS = "[CLS]"
SEP = "[SEP]"

SPECIAL_TOKENS = (PAD, UNK, CLS, SEP)

# Word runs (digits+letters) or a single other character (punctuation, map art).
_TOKEN_RE = re.compile(r"[a-z0-9]+|[^a-z0-9]")
# Map art has long runs of spaces/tabs; collapse them so state stays compact.
_WS_RE = re.compile(r"[ \t]+")


class S1Tokenizer:
    """Lowercased word+character tokenizer with head+tail truncation.

    Unknown words fall back to their individual characters, so the vocabulary
    never blocks on novel entity names.
    """

    def __init__(self, itos: List[str]):
        self.itos = list(itos)
        self.stoi = {tok: i for i, tok in enumerate(self.itos)}
        self.pad_id = self.stoi[PAD]
        self.unk_id = self.stoi[UNK]
        self.cls_id = self.stoi[CLS]
        self.sep_id = self.stoi[SEP]

    @property
    def vocab_size(self) -> int:
        return len(self.itos)

    @classmethod
    def build(cls, texts: Iterable[str], max_vocab: int = 30000, min_freq: int = 2) -> "S1Tokenizer":
        """Build a vocabulary from raw texts (states + option strings)."""
        word_counts: Counter = Counter()
        char_counts: Counter = Counter()
        for text in texts:
            norm = _WS_RE.sub(" ", text.lower())
            for tok in _TOKEN_RE.findall(norm):
                if len(tok) == 1 and not tok.isalnum():
                    char_counts[tok] += 1
                else:
                    word_counts[tok] += 1
                    for ch in tok:
                        if not ch.isalnum():
                            char_counts[ch] += 1

        itos = list(SPECIAL_TOKENS)
        # Frequent words first, then every character (they encode map art).
        budget = max(0, max_vocab - len(itos))
        words = [tok for tok, c in word_counts.most_common() if c >= min_freq]
        for tok in words[:budget]:
            if tok not in char_counts:  # a multi-char word never shadows a char id
                itos.append(tok)
        remaining = max_vocab - len(itos)
        for ch, _ in char_counts.most_common():
            if remaining <= 0:
                break
            itos.append(ch)
            remaining -= 1
        # Fallback: make sure the printable ASCII set encodes even if unseen.
        for ch in " \n[](),;:/-+=<>?!.#~0123456789":
            if ch not in {t for t in itos[len(SPECIAL_TOKENS):]} and len(itos) < max_vocab + 64:
                itos.append(ch)
        return cls(itos)

    def text_to_ids(self, text: str) -> List[int]:
        norm = _WS_RE.sub(" ", text.lower())
        ids: List[int] = []
        for tok in _TOKEN_RE.findall(norm):
            if tok in self.stoi:
                ids.append(self.stoi[tok])
            else:
                for ch in tok:
                    ids.append(self.stoi.get(ch, self.unk_id))
        return ids

    def encode(self, text: str, max_len: int) -> List[int]:
        """Encode with ``[CLS]`` prepended; overlong input keeps the head and tail.

        State blocks near the top (entity/stats) and the task hint at the tail
        are both important, so truncation keeps 70% head / 30% tail.
        """
        ids = self.text_to_ids(text)
        budget = max_len - 1
        if budget < 1:
            return [self.cls_id]
        if len(ids) > budget:
            head = int(budget * 0.7)
            tail = budget - head
            ids = ids[:head] + ids[-tail:]
        return [self.cls_id] + ids

    def decode(self, ids: List[int]) -> str:
        return "".join(self.itos[i] for i in ids if i not in (self.pad_id, self.cls_id))
