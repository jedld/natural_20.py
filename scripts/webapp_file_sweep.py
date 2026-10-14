#!/usr/bin/env python3
"""Per-file memory sweep for the n20-webapp test suite.

Runs each test FILE in its own subprocess (fresh interpreter, so any
per-file growth is isolated from the previous file), sampling RSS of the
whole process group. A watchdog kills the child if it exceeds the budget,
so no single file can OOM the machine.

Usage:
    python scripts/webapp_file_sweep.py [--budget-mb 6000] [--out report.json]
                                        [extra pytest args...]

Environment:
    N20_SWEEP_BUDGET_MB  - per-file RSS budget (default 6000)
    N20_SWEEP_TIMEOUT_S  - per-file wall-clock timeout (default 600)
    N20_SWEEP_FILES      - comma-separated list of files to run (default: all)
"""
import json
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SUITE = REPO / 'n20-webapp' / 'tests' / 'webapp'

BUDGET_MB = int(os.environ.get('N20_SWEEP_BUDGET_MB', '6000'))
TIMEOUT_S = int(os.environ.get('N20_SWEEP_TIMEOUT_S', '600'))
ONLY = os.environ.get('N20_SWEEP_FILES', '')


def group_rss_mb(pid):
    """Total RSS of the process group of pid (MB)."""
    try:
        import resource
        pgid = os.getpgid(pid)
        total = 0
        for entry in os.listdir('/proc'):
            if not entry.isdigit():
                continue
            try:
                with open(f'/proc/{entry}/stat') as f:
                    parts = f.read().rsplit(')', 1)[1].split()
                state, ppid, pgrp = parts[0], int(parts[1]), int(parts[2])
                if pgrp != pgid:
                    continue
                with open(f'/proc/{entry}/statm') as f:
                    total += int(f.read().split()[1]) * 4096 / (1024 * 1024)
            except (OSError, IndexError, ValueError):
                continue
        return total
    except Exception:
        return -1


def run_file(path: Path) -> dict:
    argv = [
        sys.executable, '-m', 'pytest', str(path),
        '-q', '-p', 'no:cacheprovider', '-p', 'no:cov', '--no-header', '-x',
    ]
    started = time.time()
    peak = 0
    timed_out = False
    killed = False
    out_lines = []
    proc = subprocess.Popen(
        argv, cwd=REPO,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        start_new_session=True,  # own process group for RSS accounting
    )
    try:
        while True:
            rc = proc.poll()
            if rc is not None:
                break
            rss = group_rss_mb(proc.pid)
            if rss > 0:
                peak = max(peak, rss)
            if rss > BUDGET_MB:
                killed = True
                break
            if time.time() - started > TIMEOUT_S:
                timed_out = True
                break
            # select() with a short timeout so the watchdog above still runs
            # while the child is silent (a hung test emits no output).
            ready, _, _ = select.select([proc.stdout], [], [], 0.5)
            if not ready:
                continue
            try:
                line = proc.stdout.readline()
            except Exception:
                break
            if not line:
                break
            out_lines.append(line.decode('utf-8', 'replace').rstrip())
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
        rc = proc.wait()
        for l in proc.stdout.readlines():
            out_lines.append(l.decode('utf-8', 'replace').rstrip())
    except Exception as e:
        rc = -1
        out_lines.append(f'sweep-error: {e}')
    tail = out_lines[-12:]
    return {
        'file': str(path.relative_to(REPO)),
        'rc': rc,
        'seconds': round(time.time() - started, 1),
        'peak_rss_mb': peak,
        'killed_by_budget': killed,
        'timed_out': timed_out,
        'tail': tail,
    }


def main():
    extra = []
    args = sys.argv[1:]
    budget_mb = BUDGET_MB
    out_path = REPO / 'test_memory_profiles' / 'webapp_file_sweep.json'
    i = 0
    while i < len(args):
        if args[i] == '--budget-mb':
            budget_mb = int(args[i + 1]); i += 2; continue
        if args[i] == '--out':
            out_path = Path(args[i + 1]); i += 2; continue
        extra.append(args[i]); i += 1

    files = sorted(SUITE.glob('test_*.py'))
    if ONLY:
        names = {n.strip() for n in ONLY.split(',') if n.strip()}
        files = [f for f in files if f.name in names or f.name in {n for n in names if n.endswith('.py')}]

    # Resume: keep previous results for files that completed cleanly with a
    # valid (non-zero) peak measurement.
    results = []
    if out_path.exists():
        try:
            prev = json.loads(out_path.read_text())
            good = {r['file'] for r in prev if r.get('peak_rss_mb', 0) > 0
                    and not r.get('killed_by_budget') and not r.get('timed_out') and r.get('rc') is not None}
            kept = [r for r in prev if r['file'] in good]
            if kept:
                print(f"[sweep] resuming: {len(kept)} files already measured, "
                      f"{len(prev) - len(kept)} will be re-run")
            results = kept
            done = {r['file'] for r in results}
            files = [f for f in files if str(f.relative_to(REPO)) not in done]
        except Exception as e:
            print(f"[sweep] could not resume from {out_path}: {e}")
    print(f"[sweep] {len(files)} files to run, budget {budget_mb} MB/file, timeout {TIMEOUT_S}s")
    for k, f in enumerate(files, 1):
        print(f"\n[sweep] ({k}/{len(files)}) {f.name} ...", flush=True)
        r = run_file(f)
        results.append(r)
        status = 'KILLED' if r['killed_by_budget'] else ('TIMEOUT' if r['timed_out'] else ('rc=%s' % r['rc']))
        print(f"[sweep]   {status}  peak {r['peak_rss_mb']} MB  {r['seconds']}s", flush=True)
        out_path.parent.mkdir(exist_ok=True)
        out_path.write_text(json.dumps(results, indent=1))
        if r['killed_by_budget'] and r['tail']:
            for line in r['tail'][-6:]:
                print(f"[sweep]     | {line[:200]}")

    print("\n[sweep] ===== FILES BY PEAK RSS =====")
    for r in sorted(results, key=lambda x: -x['peak_rss_mb'])[:20]:
        flag = ' <<<KILLED' if r['killed_by_budget'] else ''
        print(f"  {r['peak_rss_mb']:7.0f} MB  {r['seconds']:7.1f}s  {r['file']}{flag}")
    n = len(results)
    if n:
        print(f"[sweep] {n} files; avg peak {sum(r['peak_rss_mb'] for r in results) / n:.0f} MB; "
              f"files over 3GB: {sum(1 for r in results if r['peak_rss_mb'] > 3000)}")
    out_path.write_text(json.dumps(results, indent=1))
    print(f"[sweep] report: {out_path}")


if __name__ == '__main__':
    main()
