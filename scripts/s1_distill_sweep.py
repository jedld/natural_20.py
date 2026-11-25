#!/usr/bin/env python3
"""Generate a varied System One distillation corpus by sweeping battle simulations.

Drives ``scripts/s1_battle_sim.py`` (one subprocess per game so a crash in
any engine path cannot stop the sweep) across:

  * all scenarios (pc_vs_npc, duel, npc_vs_npc, pc_vs_pc, team_pvp)
  * both teacher-sides (the teacher acts on side B and, separately, side A)
  * the full SRD NPC pool and every bundled class fixture, optionally
    leveled to ``--pc-level`` (XP path + average HP + SRD spell top-ups)
  * many repeat seeds per cell

Each game's teacher request/response log lands under ``--s1-log-dir`` in the
same per-game JSONL format the webapp's live distillation logger uses, so
``scripts/export_choice_training_data.py`` ingests it unchanged::

    python scripts/s1_distill_sweep.py --repeat 6 --pc-level 5 \
        --npc-pool all --s1-log-dir logs/s1_sim/sweep
    python scripts/export_choice_training_data.py \
        --inputs 'logs/s1_sim/sweep/*.jsonl' \
        --out logs/choice_training/action_decisions_sweep.jsonl

Requires the same teacher credentials as a ``teacher`` sim arm
(``TYPESAFE_API_KEY``, loaded from ``n20-webapp/webapp/.env``).

Cost model: one game = (combatants x turns) ``decide_action`` calls, each
with a ``state + options`` prompt. ``--max-games`` caps the sweep.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SIM = os.path.join(ROOT, 'scripts', 's1_battle_sim.py')

SCENARIOS = ['pc_vs_npc', 'duel', 'npc_vs_npc', 'pc_vs_pc', 'team_pvp']


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--scenario', default=','.join(SCENARIOS),
                        help='comma-separated subset of ' + ','.join(SCENARIOS))
    parser.add_argument('--npc-pool', choices=['light', 'all'], default='all')
    parser.add_argument('--pc-level', type=int, default=5,
                        help='level fixture PCs to this level (0 = keep as-is)')
    parser.add_argument('--repeat', type=int, default=4,
                        help='games per (scenario, teacher side) cell')
    parser.add_argument('--max-rounds', type=int, default=12)
    parser.add_argument('--seed', type=int, default=770000,
                        help='sweep base seed (each game gets a unique seed)')
    parser.add_argument('--s1-log-dir', default='logs/s1_sim/sweep')
    parser.add_argument('--max-games', type=int, default=0,
                        help='stop after this many games (0 = no cap)')
    parser.add_argument('--game-timeout', type=int, default=900,
                        help='seconds per game before it is killed and skipped')
    parser.add_argument('--dry-run', action='store_true',
                        help='print the game plan without running it')
    args = parser.parse_args()

    scenarios = [s.strip() for s in args.scenario.split(',') if s.strip()]
    bad = [s for s in scenarios if s not in SCENARIOS]
    if bad:
        print(f"unknown scenario(s): {bad}; choose from {SCENARIOS}",
              file=sys.stderr)
        sys.exit(2)

    pc_level = args.pc_level or None
    plan = []
    for si, (scenario, teacher_side) in enumerate(
            itertools.product(scenarios, ['a', 'b'])):
        for i in range(args.repeat):
            seed = args.seed + si * 1000 + i
            if teacher_side == 'b':
                cmd = [sys.executable, SIM, '--scenario', scenario,
                       '--side-a-ai', 'generic', '--side-b-ai', 'teacher']
            else:
                cmd = [sys.executable, SIM, '--scenario', scenario,
                       '--side-a-ai', 'teacher', '--side-b-ai', 'random']
            cmd += ['--npc-pool', args.npc_pool, '--max-rounds',
                    str(args.max_rounds), '--seed', str(seed), '--quiet',
                    '--s1-log-dir', args.s1_log_dir]
            if pc_level:
                cmd += ['--pc-level', str(pc_level)]
            plan.append((scenario, teacher_side, seed, cmd))

    print(f"plan: {len(plan)} games "
          f"({len(scenarios)} scenarios x 2 teacher sides x {args.repeat} repeats), "
          f"npc_pool={args.npc_pool} pc_level={pc_level} "
          f"max_rounds={args.max_rounds}")
    if args.dry_run:
        for scenario, jev_side, seed, cmd in plan[:6]:
            print(' '.join(cmd))
        if len(plan) > 6:
            print(f"... {len(plan) - 6} more")
        return

    os.makedirs(args.s1_log_dir, exist_ok=True)
    t0 = time.time()
    done = ok = failed = skipped = 0
    for scenario, teacher_side, seed, cmd in plan:
        if args.max_games and done >= args.max_games:
            print(f"max-games {args.max_games} reached; stopping")
            break
        # Deterministic seeds: a completed game's log means the exact same
        # game is already distilled; don't pay for the teacher twice.
        side_a = 'teacher' if teacher_side == 'a' else 'generic'
        side_b = 'teacher' if teacher_side == 'b' else 'random'
        expected = os.path.join(
            args.s1_log_dir,
            f"{scenario}_{seed}g0_{side_a}_vs_{side_b}.s1.jsonl")
        if os.path.exists(expected) and os.path.getsize(expected) > 0:
            skipped += 1
            print(f"  [skip] {scenario} teacher={teacher_side} seed={seed} "
                  f"(log exists)", flush=True)
            continue
        done += 1
        try:
            proc = subprocess.run(cmd, cwd=ROOT, capture_output=True,
                                  text=True, timeout=args.game_timeout)
            good = proc.returncode == 0
        except subprocess.TimeoutExpired:
            proc = None
            good = False
        if good:
            ok += 1
        else:
            failed += 1
            if proc is not None and proc.stderr:
                # Surface the traceback tail; the sweep must stay diagnosable.
                err = proc.stderr.strip().splitlines()[-4:]
                print("        stderr: " + ' | '.join(err), flush=True)
        print(f"  [{done}] {scenario} teacher={teacher_side} seed={seed} "
              f"{'ok' if good else 'FAIL'}", flush=True)

    elapsed = time.time() - t0
    logs = [f for f in os.listdir(args.s1_log_dir) if f.endswith('.jsonl')]
    lines = sum(1 for f in logs
                for _ in open(os.path.join(args.s1_log_dir, f), 'rb'))
    print(f"sweep done: {done} games ({ok} ok, {failed} failed, "
          f"{skipped} skipped) in {elapsed / 60:.1f} min; "
          f"{len(logs)} log files, {lines} raw lines")
    # The exporter's default inputs already include logs/s1_sim/**/*.jsonl,
    # so a plain re-export merges the sweep into the main training corpus.
    print("next: python scripts/export_choice_training_data.py   "
          "(default inputs include the sweep dir)")


if __name__ == '__main__':
    main()
