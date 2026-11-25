#!/usr/bin/env python3
"""Train a local System One-style System One choice model from scratch.

Distills the TypeSafe teacher decision model using the exported request/response
dataset (see ``scripts/export_choice_training_data.py``): each example is a
battle state, the full legal action menu, and JEV's chosen index plus its
teacher probability vector. The model is trained with a soft
(KL against the teacher distribution) + hard (cross-entropy on the chosen
index) objective, so the local clone reproduces both JEV's pick and its
calibrated confidence.

Usage:
    python scripts/train_s1_local.py                        # default dataset
    python scripts/train_s1_local.py --inputs logs/choice_training/action_decisions_dedup.jsonl \
        --epochs 40 --out logs/s1_local/model.pt

The checkpoint is loaded by ``scripts/s1_local_api_server.py`` which serves
the TypeSafe wire protocol (``POST /v1/systemone``) so the engine's
``JevProvider`` / ``typesafe_sdk`` client can be pointed at it with
``BATTLE_TYPESAFE_BASE_URL=http://127.0.0.1:8902``.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from s1_local.data import (S1ChoiceDataset, collate, fit_tokenizer,   # noqa: E402
                            load_records, split_records)
from s1_local.model import S1Config, S1SystemOne                     # noqa: E402

DEFAULT_INPUTS = [
    'logs/choice_training/action_decisions_dedup.jsonl',
    'logs/choice_training/action_decisions.jsonl',
]


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def soft_kd_loss(logits, target, hard, option_mask, hard_weight=0.3, label_smoothing=0.05):
    """KL(teacher || student) over real options + weighted hard cross-entropy.

    ``target`` is the teacher probability vector (0 in padded slots);
    padded options are excluded from every term.
    """
    neg = -1e9
    log_probs = F.log_softmax(logits.masked_fill(option_mask == 0, neg), dim=-1)
    probs = F.softmax(logits.masked_fill(option_mask == 0, neg), dim=-1)

    # KL term: sum over real options only.
    kl = -(target * log_probs * option_mask).sum(dim=-1)
    # subtract the constant teacher entropy only via -sum p log p (kept: target
    # also appears in gradient? no: target is constant; keep full KL for readable metric)
    teacher_ent = -(target * torch.log(target.clamp_min(1e-9)) * option_mask).sum(dim=-1)
    kl = kl - teacher_ent  # pure KL divergence (student entropy - teacher entropy form)

    # Hard CE with label smoothing across real options.
    n_real = option_mask.sum(dim=-1, keepdim=True)
    smooth = (1.0 - label_smoothing) * target + label_smoothing * option_mask / n_real.clamp_min(1)
    hard_loss = -(smooth * log_probs * option_mask).sum(dim=-1)

    return (1.0 - hard_weight) * kl + hard_weight * hard_loss, kl, hard_loss


def evaluate(model, loader, device):
    model.eval()
    stats = {'n': 0, 'agree_hard': 0, 'agree_teacher': 0, 'kl': 0.0, 'ce': 0.0,
             'conf_mean': 0.0, 'teacher_conf_mean': 0.0, 'ece_bins': {}}
    with torch.no_grad():
        for batch in loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            logits = model(batch['state_ids'], batch['state_mask'],
                           batch['option_ids'], batch['option_mask'],
                           batch['option_token_mask'])
            logits = logits.float()
            mask = batch['option_mask']
            logits = logits.masked_fill(mask == 0, -1e9)
            probs = F.softmax(logits, dim=-1)
            target = batch['target']
            log_probs = F.log_softmax(logits, dim=-1)
            teacher_ent = -(target * torch.log(target.clamp_min(1e-9)) * mask).sum(-1)
            kl = (-(target * log_probs * mask).sum(-1) - teacher_ent)
            pred = probs.argmax(dim=-1)
            teacher_pick = target.argmax(dim=-1)
            b = pred.shape[0]
            stats['n'] += b
            stats['agree_hard'] += int((pred == batch['hard']).sum())
            stats['agree_teacher'] += int((pred == teacher_pick).sum())
            stats['kl'] += float(kl.sum())
            top_conf = probs.max(dim=-1).values
            stats['conf_mean'] += float(top_conf.sum())
            stats['teacher_conf_mean'] += float(target.max(dim=-1).values.sum())
    n = max(1, stats['n'])
    return {
        'examples': stats['n'],
        'top1_vs_chosen': stats['agree_hard'] / n,
        'top1_vs_teacher': stats['agree_teacher'] / n,
        'kl_vs_teacher': stats['kl'] / n,
        'student_confidence': stats['conf_mean'] / n,
        'teacher_confidence': stats['teacher_conf_mean'] / n,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--inputs', nargs='*', default=DEFAULT_INPUTS,
                    help='JSONL training files (default: exported teacher logs)')
    ap.add_argument('--out', default='logs/s1_local/model.pt', help='checkpoint path')
    ap.add_argument('--report', default=None, help='metrics JSON path (default: <out>.report.json)')
    ap.add_argument('--epochs', type=int, default=30)
    ap.add_argument('--batch-size', type=int, default=32)
    ap.add_argument('--lr', type=float, default=3e-4)
    ap.add_argument('--weight-decay', type=float, default=0.01)
    ap.add_argument('--warmup-steps', type=int, default=200)
    ap.add_argument('--hard-weight', type=float, default=0.3,
                    help='weight of hard CE vs soft KL distillation loss')
    ap.add_argument('--label-smoothing', type=float, default=0.05)
    ap.add_argument('--val-fraction', type=float, default=0.1)
    ap.add_argument('--seed', type=int, default=13)
    ap.add_argument('--max-vocab', type=int, default=30000)
    ap.add_argument('--max-state-len', type=int, default=1024)
    ap.add_argument('--max-option-len', type=int, default=64)
    ap.add_argument('--max-options', type=int, default=64,
                    help='training cap on menu size (JEV API allows up to 255)')
    ap.add_argument('--d-model', type=int, default=256)
    ap.add_argument('--n-heads', type=int, default=8)
    ap.add_argument('--state-layers', type=int, default=4)
    ap.add_argument('--option-layers', type=int, default=2)
    ap.add_argument('--cross-layers', type=int, default=2)
    ap.add_argument('--mem-slots', type=int, default=48,
                    help='Perceiver slots options attend to (0 = attend to every '
                         'state token: slow, but no information bottleneck)')
    ap.add_argument('--dropout', type=float, default=0.1)
    ap.add_argument('--device', default=None, help='cuda / cpu (default: auto)')
    ap.add_argument('--bf16', action='store_true',
                    help='bfloat16 autocast on CPU (oneDNN); big speedup, same quality')
    ap.add_argument('--compile', action='store_true', help='torch.compile the model')
    ap.add_argument('--save-every', type=int, default=0,
                    help='also write <out>.ep<epoch> every N epochs (0 = off)')
    args = ap.parse_args()

    set_seed(args.seed)
    device = torch.device(args.device or ('cuda' if torch.cuda.is_available() else 'cpu'))

    paths = [p for p in args.inputs if Path(p).exists()]
    if not paths:
        print(f"ERROR: none of the input files exist: {args.inputs}\n"
              "Run scripts/export_choice_training_data.py first.", file=sys.stderr)
        return 2
    print(f"Loading distillation data from {len(paths)} file(s): {paths}")
    records = load_records(paths, max_options=args.max_options)
    if not records:
        print("ERROR: no valid records found.", file=sys.stderr)
        return 2
    train, val = split_records(records, val_fraction=args.val_fraction, seed=args.seed)
    print(f"records: {len(records)}  train: {len(train)}  val: {len(val)}")

    tok = fit_tokenizer(train, max_vocab=args.max_vocab, min_freq=2)
    print(f"vocab: {tok.vocab_size}")

    config = S1Config(
        vocab_size=tok.vocab_size, d_model=args.d_model, n_heads=args.n_heads,
        state_layers=args.state_layers, option_layers=args.option_layers,
        cross_layers=args.cross_layers, dropout=args.dropout,
        max_state_len=args.max_state_len, max_option_len=args.max_option_len,
        max_options=args.max_options,
        n_mem_slots=max(1, args.mem_slots),
    )
    model = S1SystemOne(config).to(device)
    if args.compile:
        try:
            model = torch.compile(model)
        except Exception as e:  # pragma: no cover - optional accelerator
            print(f"torch.compile unavailable ({e}); continuing eager")
    n_params = sum(p.numel() for p in model.parameters())
    print(f"model params: {n_params/1e6:.2f}M  device={device}")

    train_ds = S1ChoiceDataset(train, tok, config.max_state_len, config.max_option_len)
    val_ds = S1ChoiceDataset(val, tok, config.max_state_len, config.max_option_len)
    g = torch.Generator(); g.manual_seed(args.seed)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                              collate_fn=collate, num_workers=2, generator=g,
                              pin_memory=(device.type == 'cuda'))
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False,
                            collate_fn=collate, num_workers=2)

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    steps_per_epoch = math.ceil(len(train_ds) / args.batch_size)
    total_steps = steps_per_epoch * args.epochs

    def lr_at(step):
        if step < args.warmup_steps:
            return args.lr * (step + 1) / max(1, args.warmup_steps)
        prog = (step - args.warmup_steps) / max(1, total_steps - args.warmup_steps)
        return args.lr * 0.5 * (1.0 + math.cos(math.pi * min(1.0, prog)))

    history = []
    best_val = float('inf')
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    global_step = 0
    t0 = time.time()
    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_loss = 0.0
        epoch_kl = 0.0
        n_batches = 0
        for batch in train_loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            for param_group in opt.param_groups:
                param_group['lr'] = lr_at(global_step)
            with torch.autocast(device_type=device.type, dtype=torch.bfloat16,
                                enabled=(device.type == 'cuda' or args.bf16)):
                logits = model(batch['state_ids'], batch['state_mask'],
                               batch['option_ids'], batch['option_mask'],
                               batch['option_token_mask'])
                loss, kl, _ = soft_kd_loss(logits.float(), batch['target'], batch['hard'],
                                           batch['option_mask'],
                                           hard_weight=args.hard_weight,
                                           label_smoothing=args.label_smoothing)
            opt.zero_grad(set_to_none=True)
            loss.mean().backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            global_step += 1
            epoch_loss += float(loss.mean())
            epoch_kl += float(kl.mean())
            n_batches += 1

        metrics = evaluate(model, val_loader, device)
        metrics.update({
            'epoch': epoch,
            'train_loss': epoch_loss / max(1, n_batches),
            'train_kl': epoch_kl / max(1, n_batches),
            'lr': opt.param_groups[0]['lr'],
            'seconds': round(time.time() - t0, 1),
        })
        history.append(metrics)
        print(f"epoch {epoch:3d} | loss {metrics['train_loss']:.4f} "
              f"| val_kl {metrics['kl_vs_teacher']:.4f} "
              f"| top1(chosen) {metrics['top1_vs_chosen']:.3f} "
              f"| top1(teacher) {metrics['top1_vs_teacher']:.3f} "
              f"| conf {metrics['student_confidence']:.3f}/"
              f"{metrics['teacher_confidence']:.3f} "
              f"| {metrics['seconds']}s", flush=True)

        if metrics['kl_vs_teacher'] < best_val:
            best_val = metrics['kl_vs_teacher']
            torch.save({
                'config': config.to_dict(),
                'tokenizer_pickle': pickle.dumps(tok),
                'model_state': model.state_dict(),
                'max_options': args.max_options,
                'train_metrics': history[-1],
                'best_val_kl': best_val,
                'trained_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'model_name': 's1-local-1',
                'dataset': [str(Path(p).resolve()) for p in paths],
                'seed': args.seed,
            }, out_path)
            print(f"  -> saved best checkpoint (val KL {best_val:.4f}) to {out_path}")

        if args.save_every and epoch % args.save_every == 0:
            torch.save({'config': config.to_dict(),
                        'tokenizer_pickle': pickle.dumps(tok),
                        'model_state': model.state_dict(),
                        'max_options': args.max_options,
                        'model_name': f's1-local-1-ep{epoch}'},
                       out_path.with_suffix(f'.ep{epoch}.pt'))

    report = {
        'inputs': paths,
        'records': len(records), 'train': len(train), 'val': len(val),
        'vocab': tok.vocab_size, 'params_millions': round(n_params / 1e6, 2),
        'config': config.to_dict(),
        'hyperparams': {k: v for k, v in vars(args).items() if k not in ('inputs',)},
        'best_val_kl': best_val,
        'history': history,
        'checkpoint': str(out_path),
    }
    report_path = Path(args.report) if args.report else out_path.with_suffix('.report.json')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    print(f"report: {report_path}")
    print(f"best val KL vs teacher: {best_val:.4f}  checkpoint: {out_path}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
