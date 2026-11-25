"""Local trainable System One-style (TypeSafe "System One") decision model.

A from-scratch PyTorch re-implementation of the *choice* primitive used by the
TypeSafe teacher decision model, distilled from logged JEV requests/responses
(``scripts/export_choice_training_data.py`` -> ``logs/choice_training/*.jsonl``).

Public surface:

- :class:`s1_local.tokenizer.S1Tokenizer` — vocab-from-scratch tokenizer.
- :class:`s1_local.model.S1SystemOne` — set-scoring transformer (state +
  option list -> probability distribution over options).
- :class:`s1_local.inference.S1LocalPredictor` — checkpoint loading and
  raw-text prediction used by ``scripts/s1_local_api_server.py``.

The served wire protocol is documented in docs/JEV_NPC_BATTLE_AI.md and is
compatible with ``typesafe_sdk`` and ``webapp.llm_handler.JevProvider``
(point ``TYPESAFE_BASE_URL`` / ``BATTLE_TYPESAFE_BASE_URL`` at the server).
"""
