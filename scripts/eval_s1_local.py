#!/usr/bin/env python3
"""Evaluate a trained s1_local checkpoint against held-out teacher decisions.

Agreement is measured against the System One teacher on the validation split:

  - top-1 vs teacher  : the model picks the teacher's argmax option
  - top-1 vs chosen   : the model picks the option the engine executed
                        (the replayed decision, what actually happened in-game)
  - val KL            : soft-divergence to the teacher probability vector
  - ECE               : calibration error of the confidence vs teacher argmax

The same script doubles as a smoke test of the checkpoint -> predictor ->
decide() path used by ``scripts/s1_local_api_server.py``.

    python scripts/eval_s1_local.py --checkpoint logs/s1_local/model.pt
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import torch  # noqa: E402

from s1_local.data import (  # noqa: E402
    S1ChoiceDataset, collate, load_records, split_records,
)
from s1_local.inference import S1LocalPredictor  # noqa: E402
from torch.utils.data import DataLoader  # noqa: E402


def audit(records, raw_total: int, label: str = '') -> None:
    """Print corpus size / variety stats (menu sizes, action mix, entities).

    The corpus drives what the student can imitate: the core combat loop is
    usually well covered while item use, grappling, Help and Second Wind are
    thin. See docs/S1_LOCAL.md -> "Corpus size and variety".
    """
    import collections
    import re

    ent = collections.Counter(r.get('entity') for r in records)
    sizes = collections.Counter(min(len(r['options']), 30) for r in records)
    verbs = collections.Counter()
    for r in records:
        opt = r['options'][r['chosen_index']].lower()
        m = re.match(r'(attack|cast|use|dash|dodge|disengage|help|hide|move|shove|'
                     r'grapple|pass|second wind|attack surge|ready|look|stay|call|tell|ask|order)', opt)
        verbs[m.group(1) if m else 'other'] += 1
    n = len(records)
    dup = raw_total - n
    print(f"corpus audit{(' ' + label) if label else ''}: {raw_total} records "
          f"({n} after exact dedup, {dup} dupes), {len(ent)} entities "
          f"(top 5 = {100 * sum(c for _, c in ent.most_common(5)) / n:.0f}%)")
    big = sum(v for k, v in sizes.items() if k >= 10)
    print(f"  menus: {100 * sizes[2] / n:.0f}% two-option, {100 * big / n:.0f}% ten-option+ "
          f"(max {max(sizes)})")
    mix = ', '.join(f"{k} {100 * v / n:.0f}%" for k, v in verbs.most_common(9))
    print(f"  chosen actions: {mix}")


def evaluate(checkpoint: str, data_paths, max_records: int, batch_size: int, device: str):
    predictor = S1LocalPredictor.load(checkpoint, device=device)
    records = load_records(data_paths)
    _train, val = split_records(records, 0.1)
    if os.environ.get('S1_AUDIT', '1') != '0':
        audit(_train + val, len(records))
    print(f"split: train {len(_train)}  val {len(val)} (entity holdout, deduped)")
    if max_records:
        val = val[:max_records]
    ds = S1ChoiceDataset(val, predictor.tokenizer,
                          predictor.config.max_state_len, predictor.config.max_option_len)
    dl = DataLoader(ds, batch_size=batch_size, shuffle=False, collate_fn=collate)

    n = 0
    match_teacher = 0
    match_chosen = 0
    kl_sum = 0.0
    ece_num = 0.0
    n_oversize = 0
    lat_sum = 0.0

    for batch in dl:
        batch = {k: v.to(predictor.device) for k, v in batch.items()}
        k = batch['target'].shape[1]
        if k > predictor.max_options:
            n_oversize += batch['target'].shape[0]
            continue
        t0 = time.perf_counter()
        logits = predictor.model(batch['state_ids'], batch['state_mask'],
                                 batch['option_ids'], batch['option_mask'],
                                 batch['option_token_mask'])[:, :k]
        lat_sum += (time.perf_counter() - t0) * 1000.0
        probs = torch.softmax(logits, dim=-1)
        target = batch['target']
        hard = batch['hard']
        teacher = target.argmax(dim=-1)
        pred = probs.argmax(dim=-1)

        n += probs.shape[0]
        match_teacher += int((pred == teacher).sum())
        match_chosen += int((pred == hard).sum())
        eps = 1e-9
        kl = (target * (torch.log(target + eps) - torch.log(probs + eps))).sum(-1)
        kl_sum += float(kl.sum())
        conf = probs.max(dim=-1).values
        correct = (pred == teacher).float()
        ece_num += float(((conf - correct).abs()).sum())

    if not n:
        print("No evaluable records (all menus exceed the checkpoint option cap).")
        return 1
    print(f"checkpoint : {checkpoint}")
    print(f"device     : {predictor.device}  (params "
          f"{sum(p.numel() for p in predictor.model.parameters()) / 1e6:.2f}M)")
    print(f"records    : {n} eval ({n_oversize} skipped: >{predictor.max_options} options)")
    print(f"top-1 vs teacher   : {100.0 * match_teacher / n:5.1f}%")
    print(f"top-1 vs chosen    : {100.0 * match_chosen / n:5.1f}%")
    print(f"val KL             : {kl_sum / n:.4f}")
    print(f"ECE (vs teacher)   : {ece_num / n:.4f}")
    print(f"forward latency    : {lat_sum / n:.1f} ms/menu")
    if predictor.meta.get('trained_at'):
        print(f"trained at         : {predictor.meta['trained_at']}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--checkpoint', default='logs/s1_local/model.pt')
    ap.add_argument('--data', action='append', default=None,
                    help='decision JSONL(s); default: the training defaults')
    ap.add_argument('--max-records', type=int, default=0, help='cap val records (0 = all)')
    ap.add_argument('--batch-size', type=int, default=32)
    ap.add_argument('--device', default=None, help='cpu / cuda (default: auto)')
    args = ap.parse_args()

    if not Path(args.checkpoint).exists():
        print(f"ERROR: checkpoint not found: {args.checkpoint}", file=sys.stderr)
        return 2

    data_paths = args.data or ['logs/choice_training/action_decisions_dedup.jsonl',
                               'logs/choice_training/action_decisions.jsonl']
    missing = [p for p in data_paths if not Path(p).exists()]
    if missing:
        print(f"ERROR: missing data file(s): {missing}", file=sys.stderr)
        return 2
    return evaluate(args.checkpoint, data_paths, args.max_records,
                    args.batch_size, args.device)


if __name__ == '__main__':
    raise SystemExit(main())
