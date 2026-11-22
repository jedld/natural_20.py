#!/usr/bin/env python3
"""Seeded encounter simulation and Monte Carlo report.

Runs a fixed scenario (or the benchmark suite) on ``Battle`` with the
``generic@1`` heuristic or a uniform random policy. Dice and uuids are seeded.
LLM narration hooks are not started.

Examples:
    python scripts/encounter_sim.py \\
        --scenario benchmarks/encounters/fighters_vs_goblins.yml \\
        --trials 1000 --seed 1000

    python scripts/encounter_sim.py --suite benchmarks/suite.yml

    python scripts/encounter_sim.py \\
        --scenario benchmarks/encounters/fighters_vs_goblins.yml \\
        --trials 20 --jobs 4 --explain
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from natural20.sim.encounter import EncounterError, format_report, load_scenario, run_trials


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--scenario', default=None, help='path to one encounter YAML')
    parser.add_argument('--suite', default=None, help='path to a suite YAML listing scenarios')
    parser.add_argument('--trials', type=int, default=None,
                        help='trials per scenario (default 1, or the suite file value)')
    parser.add_argument('--seed', type=int, default=None,
                        help='first seed; trial i uses seed+i (default 1000)')
    parser.add_argument('--jobs', type=int, default=None,
                        help='process pool size; each trial reseeds its own process')
    parser.add_argument('--explain', action='store_true',
                        help='record the top three generic@1 choices on each action')
    parser.add_argument('--max-rounds', type=int, default=None,
                        help='override the scenario round cap')
    parser.add_argument('--out', default=None, help='report JSON path for a single scenario')
    parser.add_argument('--out-dir', default=None,
                        help='directory for suite reports (default logs/encounter_sim)')
    args = parser.parse_args(argv)

    if bool(args.scenario) == bool(args.suite):
        parser.error('pass exactly one of --scenario or --suite')

    try:
        if args.suite:
            _run_suite(args)
        else:
            _run_one(args)
    except EncounterError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


def _run_one(args) -> None:
    scenario = load_scenario(args.scenario)
    trials = 1 if args.trials is None else args.trials
    seed = 1000 if args.seed is None else args.seed
    jobs = 1 if args.jobs is None else args.jobs
    report = run_trials(
        args.scenario, trials, seed,
        jobs=jobs, explain=args.explain, max_rounds=args.max_rounds,
    )
    print(format_report(report))
    out = Path(args.out) if args.out else Path('logs/encounter_sim') / f"{scenario['id']}.report.json"
    _write(out, report)


def _run_suite(args) -> None:
    suite_path = Path(args.suite).resolve()
    with suite_path.open('r', encoding='utf-8') as handle:
        suite = yaml.safe_load(handle) or {}
    scenarios = suite.get('scenarios') or []
    if not scenarios:
        raise EncounterError(f"{suite_path} has no scenarios")
    trials = suite.get('trials', 2) if args.trials is None else args.trials
    seed = suite.get('seed', 1000) if args.seed is None else args.seed
    jobs = suite.get('jobs', 1) if args.jobs is None else args.jobs
    out_dir = Path(args.out_dir) if args.out_dir else Path('logs/encounter_sim')
    for entry in scenarios:
        path = Path(entry)
        if not path.is_absolute():
            path = suite_path.parent / path
        report = run_trials(
            path, trials, seed,
            jobs=jobs, explain=args.explain, max_rounds=args.max_rounds,
        )
        print(format_report(report))
        print()
        _write(out_dir / f"{report['scenario']}.report.json", report)


def _write(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Traces make a 1000-trial file large. Keep them: they are the decision log.
    with path.open('w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
        handle.write('\n')
    print(f"wrote {path}")


if __name__ == '__main__':
    raise SystemExit(main())
