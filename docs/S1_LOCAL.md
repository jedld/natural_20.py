# Local JEV-style battle model (`s1_local/`)

A small, fully local, trainable decision model that imitates TypeSafe JEV's
"System One" battle decisions, distilled from the engine's own JEV call logs.
It speaks the **same HTTP wire protocol** as `https://api.typesafe.ai`, so the
engine can be pointed at it by changing only `TYPESAFE_BASE_URL` — no engine
or webapp code changes.

```
  JEV distillation logs                train from scratch                 serve
  logs/choice_training/*.jsonl  ──►  scripts/train_s1_local.py  ──►  logs/s1_local/model.pt
  (captured by JevProvider)          (s1_local/ package)                  │
                                                                            ▼
                                              scripts/s1_local_api_server.py
                                              (FastAPI, /v1/systemone wire)
                                                                            │
                                                          TYPESAFE_BASE_URL │ (or BATTLE_TYPESAFE_BASE_URL)
                                                                            ▼
                                                          webapp JevProvider ──► VTT battle AI
```

## Why

The VTT's battle "llm" controllers normally call the hosted TypeSafe JEV
service (see [`JEV_NPC_BATTLE_AI.md`](JEV_NPC_BATTLE_AI.md)). This package
provides a self-hostable drop-in:

- **offline / air-gapped** or keyless operation,
- **free** per-decision inference (no metered API),
- a **training corpus you already own**: `JevProvider` records every
  decision it is asked to make — prompt state, the option menu, the JEV
  probability vector and the executed index — into
  `logs/choice_training/action_decisions.jsonl` (see `webapp/jev_distill.py`).

## The wire contract (compatibility)

The server implements exactly the endpoints `typesafe_sdk` and
`webapp.llm_handler.JevProvider` use:

| Endpoint | Purpose |
|---|---|
| `POST /v1/systemone` | `{"state", "model", "questions"}` → `{"model", "usage", "answers"}`; `answers[name]` is `choice` (`{type, choice, confidence, probabilities}`), `noul` (`{type, noul}`) or `score` (`{type, score, confidence, legend, probabilities}`) |
| `GET /v1/models` | lists `s1-local-1` |
| `GET /health` | liveness (not part of the wire protocol) |

Notes:

- Optional Bearer auth: start the server with `--api-key K` (or `API_KEY`) and
  set the same as `TYPESAFE_API_KEY`.
- `JevProvider` rejects choice menus longer than **255 options** (the SDK
  cardinality cap). The checkpoint's own `max_options` (train with
  `--max-options`, default 64) must cover the menus you serve; the server
  returns a 422 if a menu is larger than the checkpoint cap.
- `x-typesafe-request-id` is echoed for request correlation.
- `score` questions are answered by argmax over the rubric levels (the local
  model has no score head; `JevProvider` only consumes `score` for logging).
- `noul` questions fall back to verbalized-yes/no choice probability (no noul
  training rows exist in the distillation logs).
- Wire compatibility is covered by [`tests/test_s1_local_wire_compat.py`](../tests/test_s1_local_wire_compat.py),
  which trains a tiny model, serves it with uvicorn on a socket, and drives it
  through the **real `typesafe_sdk` client and the engine's `JevProvider`**.

## Install

Core engine/webapp do **not** depend on anything here. For train/serve/eval:

```sh
pip install -r requirements-s1-local.txt   # torch, fastapi, uvicorn, typesafe-sdk
```

## Train from scratch

```sh
python scripts/train_s1_local.py \
    --epochs 30 --batch-size 32 --lr 3e-4 --device cpu \
    --out logs/s1_local/model.pt
# inputs default to every logs/choice_training/action_decisions*.jsonl;
# pass --inputs FILE [FILE ...] to choose your own corpus
```

Defaults reproduce the reference run (a few hours on CPU, 2.34 M params):
`--d-model 192 --n-heads 8 --state-layers 0 --option-layers 1 --cross-layers 2
--mem-slots 48 --max-state-len 1024 --max-option-len 48 --max-options 64`.
Use `--device cuda` on a GPU (a few minutes instead of hours).

- Data: every `logs/choice_training/action_decisions*.jsonl`. `split_records`
  **dedups exact repeats** and then splits **by acting entity**, so a
  validation example shares no state, option menu or creature with a
  training example. A plain shuffled split is not safe on this corpus:
  91 % of its val records have an exact `(state, options)` twin in train
  (repeated sim seeds), which contaminates every val metric — measured on
  one such checkpoint, val KL reads 0.046 (contaminated) vs 0.052 (entity
  holdout); top-1 is less affected because matching the teacher's full
  probability vector needs real pattern learning, not memorization.
  Treat entity-holdout numbers as the generalization estimate.
- Objective: soft cross-entropy against the JEV probability vector (teacher
  distillation) with hard cross-entropy on the executed index
  (`--hard-weight`), KL reported on the val split.
- `model.pt` embeds the weights **and** the word tokenizer (pickled) and the
  training metadata; checkpoint load is handled by `S1LocalPredictor.load`.
  (Checkpoints pickled before the `jev_local` → `s1_local` rename still load:
  the tokenizer blob is a plain dict.)

## Corpus size and variety

Audited from the current logs (the trainer prints the split sizes on its
header line; `scripts/eval_s1_local.py` reports the val menu-size skews):

| Aspect | Value |
|---|---|
| Raw records | 16,016 |
| Unique `(state, options)` | 9,928 (≈38 % exact duplicates from repeated sim seeds; split 7,704 train / 2,224 val, entity-grouped) |
| Distinct acting entities | 108 (was 53 before the distill sweep) |
| Sources | scripted sims (`jev_requests_seed20-24`, `after_hazards`) + real `npc_vs_npc` / `team_pvp` logs + `scripts/s1_distill_sweep.py` (60 games × live JEV teacher, full bundled-NPC pool, level-5 class fixtures) |
| Menu sizes | 21 % two-option up to 9 % 30-option — the option-competition head is well exercised |
| Combat rounds | 1–14, decaying; late-round/low-HP clutch states are thinner |
| Chosen action mix | move 31 %, attack 20 %, callouts ~14 %, dash 9 %, cast 6 %, dodge 5 %, pass 5 %, disengage 3 %, hide 1 %, shove 0.7 % |
| Tail (chosen) | shove 71, stand 36, Second Wind 24, interact 22, use item 17, grapple 8 — present with real teacher preferences now (previously all < 20 records) |

So the corpus is comfortably big enough for a 2.3 M-parameter choice model and
covers the core combat loop (movement, attacks, disengage/dash/dodge, spell
selection) well. The behaviors that were effectively **absent before the sweep
— shoving, grappling, Second Wind, item use, Help — are now sampled
(2–22 % of menus contain the option) but still under 1 % of the chosen
actions**, so expect them to generalize weakest to unseen creatures.

Growing it (cheapest first):

1. **Just play** — `JevProvider` logs every decision it makes
   (`webapp/jev_distill.py`, on by default), so real sessions steadily add
   the rare action types.
2. **Simulate breadth** — `scripts/s1_distill_sweep.py` drives
   `scripts/s1_battle_sim.py` across all five scenarios, both JEV-sides, the
   full bundled-NPC pool (`--npc-pool all`), every bundled class fixture
   optionally leveled via the XP path with SRD spell top-ups
   (`--pc-level 5`), and many repeat seeds::

       python scripts/s1_distill_sweep.py --repeat 6 --pc-level 5 \
           --npc-pool all                     # ~60 games, one teacher call per decision
       python scripts/export_choice_training_data.py   # default inputs include logs/s1_sim/**

   One subprocess per game (crash-isolated), deterministic seeds, and a
   skip-if-log-exists rule, so re-runs only pay for new games. Measured effect
   of the 60-game sweep (2,452 teacher decisions, 76 distinct actors): 815
   menus containing a shove (43 teacher-chosen), 782 Help, 193 grapple, 32
   Second Wind, 68 use-item, plus heavy NPCs (ogres, gladiators, owlbears,
   specters, swarms) the light pool never exercised. `--max-games` caps cost;
   stderr tails of failed games are printed by the driver.
3. **Re-weight the tail** — the loss already takes per-record soft targets;
   up-weighting rare verbs is a small change if a specific behavior matters.

## Reference results

`scripts/eval_s1_local.py --checkpoint logs/s1_local/model_enriched.pt`
(enriched corpus above, best checkpoint = epoch 3; early-epoch checkpoint is
usually the right one on this corpus — train loss keeps falling while val KL
bottoms out early, so watch the "saved best checkpoint" lines rather than
running all 30 epochs):

| Metric | Enriched corpus | Notes |
|---|---|---|
| top-1 vs teacher argmax | **69.7 %** | vs 63.6 % (best-epoch during training, pre-sweep corpus) |
| top-1 vs executed action | 69.5 % | teacher agreement with executed ≈ 86 % |
| val KL vs teacher | **0.186** | vs 0.296 pre-sweep (best of the 30-epoch run) |
| ECE vs teacher | 0.42 | over-confident; fine for pick-the-index use, consider temperature scaling if you rely on `confidence` |
| forward latency | 0.4 ms/menu (cuda) | single menu, batch 1 |

The hosted teacher agrees with the *executed* action for ~86 % of logged
decisions, so ~85–90 % agreement is the practical ceiling for these labels;
top-1 **against the teacher's own argmax** is the purer distillation target.

## Serve (TypeSafe-compatible API)

```sh
python scripts/s1_local_api_server.py \
    --checkpoint logs/s1_local/model.pt --host 127.0.0.1 --port 5005
```

Point the engine at it:

```sh
# .env / environment — battle AI only:
BATTLE_LLM_PROVIDER=jev
BATTLE_TYPESAFE_BASE_URL=http://127.0.0.1:5005
# or for every JEV call: TYPESAFE_BASE_URL=http://127.0.0.1:5005
./start_web.sh user_levels/<campaign>
```

No API key is required unless the server was started with `--api-key`.

## Evaluate

```sh
python scripts/eval_s1_local.py --checkpoint logs/s1_local/model.pt
```

Reports top-1 vs teacher / vs executed choice, val KL, expected calibration
error and forward latency on the held-out split.

## Architecture (`s1_local/`)

| Module | Role |
|---|---|
| `tokenizer.py` | word-level tokenizer with `[UNK]` fallback; pickled into checkpoints |
| `data.py` | JSONL loading, entity-level train/val split, padding/collate |
| `model.py` | `JevSystemOne`: bag-of-words embed → optional Transformer state stack (RoPE + sliding window, handles the ~3k-char state cheaply) → per-option mean-pool → gated additive attention over options (TypeSafe's System One option-competition head) with memory slots → Transformer cross layers → scalar logit per option |
| `inference.py` | checkpoint loading + raw-text `decide()` + wire-format `answer_questions()` |
| `server.py` | FastAPI wire app (`build_app(predictor, api_key=...)`) |

Scripts: `scripts/train_s1_local.py`, `scripts/s1_local_api_server.py`,
`scripts/eval_s1_local.py`.

## Data capture

`JevProvider` logs each decision (`webapp/jev_distill.py`) whenever
`JEV_DISTILL_ENABLED` is not `0` (on by default when `logs/` is writable).
The distillation file also doubles as the dataset for this model — more play
with the hosted teacher → more training rows → a better local student.

## Tests

```sh
python -m pytest tests/test_s1_local_wire_compat.py   # needs torch+fastapi+typesafe-sdk
```
