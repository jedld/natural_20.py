"""System One-style System One model, train locally from scratch.

The engine drives TypeSafe's JEV "System One" model through
``webapp/llm_handler.JevProvider``: it sends one ``state`` string plus a set of
``choice`` questions whose ``criteria`` are the *full legal action menu*, and
JEV returns an index, a chosen label and a full probability distribution over
the options. This module reproduces that contract with a small, fully local
transformer so the clone can be trained (and run) without the hosted API.

Architecture (the same "score every legal option" paradigm as JEV):

- hashed wordpiece embedding shared by state and options
- an optional self-attention stack over the state tokens (fast path: none)
- one self-attention stack per option (cheap: ``max_option_len`` per option,
  options never attend to each other)
- option tokens cross-attend to the state token sequence (shared memory, so
  the state is encoded once regardless of menu size)
- per-option score head -> softmax over options

Cost is dominated by the option->state cross attention: ``K * L_opt * L_state``.
``state_layers`` is therefore the main knob for trading quality against CPU
training time (``--state-layers 0`` disables state self-attention).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

import torch
import torch.nn.functional as F
from torch import nn


@dataclass
class S1Config:
    vocab_size: int = 32000
    d_model: int = 256
    n_heads: int = 8
    state_layers: int = 2
    option_layers: int = 1
    cross_layers: int = 2
    dropout: float = 0.1
    max_state_len: int = 1024
    max_option_len: int = 64
    max_options: int = 64
    # Perceiver bottleneck: learned slots that options cross-attend to instead
    # of every state token (the state can be >1k tokens; menus up to 64).
    n_mem_slots: int = 48

    def __post_init__(self):
        # n_mem_slots <= 0 means "no bottleneck": options cross-attend to every
        # state token (accurate but O(K * L_opt * L_state) -- slow on CPU).
        if self.n_mem_slots == 0:
            self.n_mem_slots = -1

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "S1Config":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class AttentionPool(nn.Module):
    def __init__(self, d_model: int):
        super().__init__()
        self.score = nn.Linear(d_model, 1)

    def forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        logits = self.score(x).squeeze(-1)
        logits = logits.masked_fill(mask == 0, -1e4)
        w = torch.softmax(logits, dim=1)
        return torch.einsum("bt,btd->bd", w, x)


def _key_mask(mask: torch.Tensor, dtype: torch.dtype) -> torch.Tensor:
    """(B, T) 1=real -> additive (B, 1, 1, T) attention bias."""
    return (1.0 - mask.unsqueeze(1).unsqueeze(1).to(dtype)) * -1e4


class SelfAttnBlock(nn.Module):
    """Pre-LN self-attention + FFN over one sequence (B, T, d)."""

    def __init__(self, d_model: int, n_heads: int, dropout: float):
        super().__init__()
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads
        self.qkv = nn.Linear(d_model, 3 * d_model)
        self.proj = nn.Linear(d_model, d_model)
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.ff = nn.Sequential(
            nn.Linear(d_model, d_model * 4), nn.GELU(), nn.Dropout(dropout),
            nn.Linear(d_model * 4, d_model),
        )
        self.drop = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        B, T, D = x.shape
        h = self.norm1(x)
        qkv = self.qkv(h).view(B, T, 3, self.n_heads, self.head_dim).permute(2, 0, 3, 1, 4)
        q, k, v = qkv[0], qkv[1], qkv[2]
        attn = F.scaled_dot_product_attention(
            q, k, v, attn_mask=_key_mask(mask, q.dtype),
            dropout_p=self.drop.p if self.training else 0.0)
        attn = attn.transpose(1, 2).reshape(B, T, D)
        x = x + self.drop(self.proj(attn))
        x = x + self.ff(self.norm2(x))
        return x


class CrossAttnBlock(nn.Module):
    """Pre-LN cross-attention (queries: options) over shared memory (state)."""

    def __init__(self, d_model: int, n_heads: int, dropout: float):
        super().__init__()
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads
        self.q = nn.Linear(d_model, d_model)
        self.kv = nn.Linear(d_model, 2 * d_model)
        self.proj = nn.Linear(d_model, d_model)
        self.norm_q = nn.LayerNorm(d_model)
        self.norm_kv = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.ff = nn.Sequential(
            nn.Linear(d_model, d_model * 4), nn.GELU(), nn.Dropout(dropout),
            nn.Linear(d_model * 4, d_model),
        )
        self.drop = nn.Dropout(dropout)

    def forward(self, q_x: torch.Tensor, mem: torch.Tensor, mem_mask: torch.Tensor) -> torch.Tensor:
        B, Tq, D = q_x.shape
        Tk = mem.shape[1]
        h_q = self.norm_q(q_x)
        q = self.q(h_q).view(B, Tq, self.n_heads, self.head_dim).transpose(1, 2)
        h_kv = self.norm_kv(mem)
        kv = self.kv(h_kv).view(B, Tk, 2, self.n_heads, self.head_dim).permute(2, 0, 3, 1, 4)
        k, v = kv[0], kv[1]
        attn = F.scaled_dot_product_attention(
            q, k, v, attn_mask=_key_mask(mem_mask, q.dtype),
            dropout_p=self.drop.p if self.training else 0.0)
        attn = attn.transpose(1, 2).reshape(B, Tq, D)
        q_x = q_x + self.drop(self.proj(attn))
        q_x = q_x + self.ff(self.norm2(q_x))
        return q_x


class S1SystemOne(nn.Module):
    def __init__(self, config: S1Config):
        super().__init__()
        self.config = config
        d = config.d_model
        self.embed = nn.Embedding(config.vocab_size, d, padding_idx=0)
        self.role_embed = nn.Embedding(2, d)     # 0 = state token, 1 = option token
        self.state_pos = nn.Embedding(config.max_state_len + 2, d)
        self.option_pos = nn.Embedding(config.max_option_len + 2, d)
        self.drop = nn.Dropout(config.dropout)

        self.state_blocks = nn.ModuleList(
            [SelfAttnBlock(d, config.n_heads, config.dropout) for _ in range(config.state_layers)])
        self.state_norm = nn.LayerNorm(d)
        self.state_pool = AttentionPool(d)

        # Perceiver-style bottleneck: a few learned slots read the (long) state,
        # so the menu-sized option queries only ever cross-attend to slots.
        if config.n_mem_slots > 0:
            self.mem_slots = nn.Parameter(torch.randn(config.n_mem_slots, d) * 0.02)
            self.slot_blocks = nn.ModuleList(
                [CrossAttnBlock(d, config.n_heads, config.dropout) for _ in range(1)])
            self.slot_norm = nn.LayerNorm(d)

        self.option_blocks = nn.ModuleList(
            [SelfAttnBlock(d, config.n_heads, config.dropout) for _ in range(config.option_layers)])
        self.cross_blocks = nn.ModuleList(
            [CrossAttnBlock(d, config.n_heads, config.dropout) for _ in range(config.cross_layers)])
        self.option_norm = nn.LayerNorm(d)
        self.option_pool = nn.Linear(d, 1)

        self.score = nn.Sequential(
            nn.Linear(3 * d, d), nn.GELU(), nn.Dropout(config.dropout), nn.Linear(d, 1))
        self.noul_head = nn.Sequential(
            nn.Linear(2 * d, d), nn.GELU(), nn.Dropout(config.dropout), nn.Linear(d, 2))

    # ------------------------------------------------------------------ #
    def _embed(self, ids: torch.Tensor, pos: nn.Embedding, role: int) -> torch.Tensor:
        _, L = ids.shape
        p = torch.arange(L, device=ids.device).unsqueeze(0)
        x = self.embed(ids) + pos(p)
        return self.drop(x + self.role_embed(
            torch.full(ids.shape, role, dtype=torch.long, device=ids.device)))

    def encode_state(self, state_ids: torch.Tensor, state_mask: torch.Tensor):
        """Return (memory, memory_mask, state_vec). ``memory`` is the small slot
        sequence every option cross-attends to; cheap regardless of state length."""
        x = self._embed(state_ids, self.state_pos, 0)
        for block in self.state_blocks:
            x = block(x, state_mask)
        x = self.state_norm(x)
        state_vec = self.state_pool(x, state_mask)
        B = x.shape[0]
        if self.config.n_mem_slots <= 0:
            return x, state_mask, state_vec
        slots = self.mem_slots.unsqueeze(0).expand(B, -1, -1)
        for block in self.slot_blocks:
            slots = block(slots, x, state_mask)
        slots = self.slot_norm(slots)
        slot_mask = torch.ones(B, slots.shape[1], device=x.device, dtype=state_mask.dtype)
        return slots, slot_mask, state_vec

    def encode_options(self, option_ids: torch.Tensor, option_token_mask: torch.Tensor,
                       memory: torch.Tensor, memory_mask: torch.Tensor) -> torch.Tensor:
        """option_ids: (B, K, Lo); option_token_mask: (B, K, Lo); memory: (B, S, d)
        where S = n_mem_slots (so the menu-cost is K * Lo * S, not K * Lo * L_state).

        Option self-attention runs per option (options are scored independently,
        so they must not mix); the cross-attention queries are flattened to
        (B, K*Lo) so the state memory is shared across the whole menu.
        """
        B, K, Lo = option_ids.shape
        x = self._embed(option_ids.reshape(B * K, Lo), self.option_pos, 1)
        tok_flat = option_token_mask.reshape(B * K, Lo)
        for block in self.option_blocks:
            x = block(x, tok_flat)
        x = x.view(B, K * Lo, -1)
        for block in self.cross_blocks:
            x = block(x, memory, memory_mask)
        x = x.view(B, K, Lo, -1)
        logits = self.option_pool(x).squeeze(-1)                # (B, K, Lo)
        logits = logits.masked_fill(option_token_mask == 0, -1e4)
        w = torch.softmax(logits, dim=2)
        return self.option_norm(torch.einsum("bkl,bkld->bkd", w, x))

    # ------------------------------------------------------------------ #
    def forward(self, state_ids: torch.Tensor, state_mask: torch.Tensor,
                option_ids: torch.Tensor, option_mask: torch.Tensor,
                option_token_mask: torch.Tensor = None) -> torch.Tensor:
        """Return choice logits ``(B, K)``. ``option_mask`` marks real options
        (padding slots get a constant score and are masked by the caller)."""
        if option_token_mask is None:
            option_token_mask = (option_ids != 0).float()
        memory, memory_mask, state_vec = self.encode_state(state_ids, state_mask)
        opt_vec = self.encode_options(option_ids, option_token_mask, memory, memory_mask)
        K = opt_vec.shape[1]
        state_exp = state_vec.unsqueeze(1).expand(B := opt_vec.shape[0], K, -1)
        pair = opt_vec * state_exp
        feats = torch.cat([opt_vec, state_exp, pair], dim=-1)
        logits = self.score(feats).squeeze(-1)
        logits = logits.masked_fill(option_mask == 0, -1e9)
        return logits

    @torch.no_grad()
    def predict_noul(self, state_ids: torch.Tensor, state_mask: torch.Tensor) -> torch.Tensor:
        """Yes/no fallback head. Distillation logs contain no noul answers, so
        this head stays untrained; JevProvider falls back to 0.5 for noul."""
        _, _, state_vec = self.encode_state(state_ids, state_mask)
        return torch.sigmoid(self.noul_head(state_vec))[:, 1]
