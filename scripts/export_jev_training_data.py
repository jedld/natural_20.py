#!/usr/bin/env python3
"""Export JEV request/response JSONL logs into clean training records.

Reads the raw ``JevProvider`` request logs written by
``scripts/simulate_priest_quarters.py --jev-log`` and
``scripts/jev_battle_sim.py --jev-log-dir`` and produces a compact, validated
JSONL dataset suitable for training a similar System One action-choice model.

Only successful ``task == "action"`` records are exported. Each output record
contains the rendered state, the full option list, the chosen index/option,
confidence, the raw probability map, and a probability vector aligned to the
option list.

Usage:
    python scripts/export_jev_training_data.py \
        --out logs/jev_training/action_decisions.jsonl \
        --report logs/jev_training/action_decisions.report.json
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_INPUTS = [
    'logs/compare/jev_requests_*.jsonl',
    'logs/jev_requests_*.jsonl',
    'logs/jev_sim/**/*.jsonl',
    'logs/jev_training/raw/**/*.jsonl',
]


def expand_inputs(patterns):
    files = []
    seen = set()
    for pattern in patterns:
        path = Path(pattern)
        candidates = []
        if path.is_dir():
            candidates.extend(path.glob('**/*.jsonl'))
        elif any(ch in pattern for ch in '*?['):
            candidates.extend(Path(p) for p in glob.glob(pattern, recursive=True))
        else:
            candidates.append(path)
        for candidate in candidates:
            candidate = candidate.resolve()
            if candidate in seen or not candidate.is_file():
                continue
            seen.add(candidate)
            files.append(candidate)
    return sorted(files)


def probability_vector(probs, options):
    """Align a JEV probability map to the option list.

    JEV returns probabilities keyed by stringified option index. Missing
    indices become 0.0. If the present probabilities do not sum to 1.0, the
    vector is renormalized so it can be used directly as a soft label.
    """
    vec = [0.0] * len(options)
    if isinstance(probs, dict):
        for key, value in probs.items():
            try:
                idx = int(str(key))
            except (TypeError, ValueError):
                continue
            if not 0 <= idx < len(vec):
                continue
            try:
                vec[idx] = max(0.0, float(value))
            except (TypeError, ValueError):
                continue
    total = sum(vec)
    if total > 0:
        vec = [value / total for value in vec]
    return vec


def parse_state(state):
    info = {}
    if not state:
        return info
    first = state.splitlines()[0] if state else ''
    m = re.search(r'Entity:\s*(?P<entity>.*?);\s*HP', first)
    if m:
        info['entity'] = m.group('entity').strip()
    m = re.search(r'HP\s+(?P<hp>\d+)/(?P<max_hp>\d+)', state)
    if m:
        info['hp'] = int(m.group('hp'))
        info['max_hp'] = int(m.group('max_hp'))
    m = re.search(r'\bAC\s+(?P<ac>\d+)', state)
    if m:
        info['ac'] = int(m.group('ac'))
    m = re.search(r'pos\s*\[(?P<x>\d+),\s*(?P<y>\d+)\]', state)
    if m:
        info['position'] = [int(m.group('x')), int(m.group('y'))]
    m = re.search(r'\nround\s+(?P<round>\d+);', state)
    if m:
        info['round'] = int(m.group('round'))
    return info


def clean_record(record, source, line_no):
    """Return (clean_record, rejection_reason)."""
    if not isinstance(record, dict):
        return None, 'not_object'
    task = record.get('task')
    if task == 'bool':
        return None, 'bool_task'
    if record.get('error') is not None:
        return None, 'error_record'
    response = record.get('response')
    if not isinstance(response, dict):
        return None, 'no_response'
    if task != 'action':
        return None, f'unexpected_task:{task}'
    request = record.get('request') or {}
    state = request.get('state') or ''
    options = request.get('options') or []
    if not isinstance(state, str) or not state.strip():
        return None, 'missing_state'
    if not isinstance(options, list) or not options:
        return None, 'missing_options'
    parsed = response.get('parsed') or {}
    index = parsed.get('index')
    if isinstance(index, bool) or not isinstance(index, int):
        return None, 'missing_index'
    if not 0 <= index < len(options):
        return None, 'index_out_of_range'
    confidence = parsed.get('confidence')
    probabilities = parsed.get('probabilities')
    state_info = parse_state(state)
    sim = record.get('sim') or {}
    clean = {
        'source_file': str(source),
        'line_no': line_no,
        'timestamp': record.get('timestamp'),
        'model': record.get('model'),
        'task': task,
        'instructions': request.get('instructions'),
        'state': state,
        'options': [str(option) for option in options],
        'chosen_index': index,
        'chosen_option': str(options[index]),
        'confidence': confidence,
        'probabilities': probabilities,
        'probability_vector': probability_vector(probabilities, options),
        'latency_ms': record.get('latency_ms'),
        'entity': state_info.get('entity'),
        'round': state_info.get('round'),
        'hp': state_info.get('hp'),
        'max_hp': state_info.get('max_hp'),
        'ac': state_info.get('ac'),
        'position': state_info.get('position'),
        'sim': sim,
    }
    return clean, None


def percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def summarize(name, values):
    if not values:
        return None
    return {
        'count': len(values),
        'mean': round(statistics.fmean(values), 3),
        'median': round(statistics.median(values), 3),
        'min': round(min(values), 3),
        'max': round(max(values), 3),
        'p95': round(percentile(values, 0.95), 3),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--inputs', nargs='*', default=None,
                        help='JSONL files, directories, or glob patterns. '
                             f'Default: {DEFAULT_INPUTS}')
    parser.add_argument('--out', default='logs/jev_training/action_decisions.jsonl',
                        help='Output JSONL path.')
    parser.add_argument('--report', default='logs/jev_training/action_decisions.report.json',
                        help='Output JSON report path.')
    parser.add_argument('--dedupe', action='store_true',
                        help='Drop records with identical state/options/chosen_index.')
    args = parser.parse_args()

    input_files = expand_inputs(args.inputs or DEFAULT_INPUTS)
    out_path = (ROOT / args.out).resolve()
    report_path = (ROOT / args.report).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    rejection_reasons = Counter()
    source_counts = Counter()
    model_counts = Counter()
    entity_counts = Counter()
    option_counts = []
    state_chars = []
    latencies = []
    confidences = []
    seen_keys = set()
    exported = 0
    valid = 0
    read = 0
    json_errors = 0
    duplicate_exact = 0

    with out_path.open('w', encoding='utf-8') as out_handle:
        for source in input_files:
            with source.open('r', encoding='utf-8') as handle:
                for line_no, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    read += 1
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        json_errors += 1
                        rejection_reasons['json_decode_error'] += 1
                        continue
                    clean, reason = clean_record(record, source, line_no)
                    if reason:
                        rejection_reasons[reason] += 1
                        continue
                    valid += 1
                    key = hashlib.sha256(json.dumps(
                        [clean['state'], clean['options'], clean['chosen_index']],
                        sort_keys=True,
                        separators=(',', ':'),
                    ).encode('utf-8')).hexdigest()
                    if args.dedupe and key in seen_keys:
                        duplicate_exact += 1
                        continue
                    seen_keys.add(key)
                    out_handle.write(json.dumps(clean, separators=(',', ':')) + '\n')
                    exported += 1
                    source_counts[str(source.relative_to(ROOT) if source.is_relative_to(ROOT) else source)] += 1
                    model_counts[str(clean.get('model'))] += 1
                    if clean.get('entity'):
                        entity_counts[clean['entity']] += 1
                    option_counts.append(len(clean['options']))
                    state_chars.append(len(clean['state']))
                    if isinstance(clean.get('latency_ms'), (int, float)):
                        latencies.append(float(clean['latency_ms']))
                    if isinstance(clean.get('confidence'), (int, float)):
                        confidences.append(float(clean['confidence']))

    report = {
        'input_files': [str(f.relative_to(ROOT) if f.is_relative_to(ROOT) else f) for f in input_files],
        'records_read': read,
        'json_errors': json_errors,
        'valid_action_records': valid,
        'exported_records': exported,
        'duplicate_exact_dropped': duplicate_exact,
        'rejected': dict(rejection_reasons),
        'models': dict(model_counts),
        'source_files': dict(source_counts),
        'top_entities': dict(entity_counts.most_common(10)),
        'option_count': summarize('option_count', option_counts),
        'state_chars': summarize('state_chars', state_chars),
        'latency_ms': summarize('latency_ms', latencies),
        'confidence': summarize('confidence', confidences),
        'out': str(out_path.relative_to(ROOT) if out_path.is_relative_to(ROOT) else out_path),
    }
    with report_path.open('w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
        handle.write('\n')

    print(f"input files: {len(input_files)}")
    print(f"records read: {read}")
    print(f"valid action records: {valid}")
    print(f"exported: {exported}")
    print(f"rejected: {dict(rejection_reasons)}")
    print(f"report: {report_path}")


if __name__ == '__main__':
    sys.exit(main())
