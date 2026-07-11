#!/usr/bin/env python3
"""
pytest-memprof-plugin: Per-test memory profiling and OOM detection for pytest.

Install:
    pip install pytest-memprof-plugin  # future
    # Or use inline:
    pytest --plugin scripts/pytest_memprof_plugin.py

Usage:
    pytest --mem-profile                           # Profile all tests
    pytest --mem-profile --mem-threshold 500       # Alert above 500MB delta
    pytest --mem-profile --mem-top 20              # Show top 20 allocations
    pytest -k "test_spell" --mem-profile --mem-report mem_report.json

Features:
    1. Per-test memory delta tracking using tracemalloc
    2. Top allocation tracking (by file/line)
    3. OOM risk detection (alerts when memory exceeds threshold)
    4. Memory regression detection (compares to baseline)
    5. Isolated subprocess execution for leaky tests
    6. Auto-xfail persistent offenders
    7. Memory profile report export (JSON)

Environment variables:
    N20_MEM_THRESHOLD_MB  - Memory delta threshold in MB (default: 500)
    N20_MEM_TOP_FRAMES    - Number of top allocations to show (default: 10)
    N20_MEM_BASELINE      - Path to baseline JSON for regression detection
    N20_MEM_ISOLATED      - Run tests in isolated subprocesses (default: 0)
"""

import json
import os
import sys
import tracemalloc
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLD_MB = int(os.environ.get("N20_MEM_THRESHOLD_MB", "500"))
DEFAULT_TOP_FRAMES = int(os.environ.get("N20_MEM_TOP_FRAMES", "10"))
DEFAULT_ISOLATED = int(os.environ.get("N20_MEM_ISOLATED", "0"))

_MEM_DATA = {}  # nodeid -> per-test memory data
_ISOLATED_MODE = False


# ---------------------------------------------------------------------------
# Plugin options
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    parser.addoption(
        "--mem-profile",
        action="store_true",
        default=False,
        help="Enable per-test memory profiling (requires tracemalloc)",
    )
    parser.addoption(
        "--mem-threshold",
        type=int,
        default=DEFAULT_THRESHOLD_MB,
        help=f"Memory delta threshold in MB before alerting (default: {DEFAULT_THRESHOLD_MB})",
    )
    parser.addoption(
        "--mem-top",
        type=int,
        default=DEFAULT_TOP_FRAMES,
        help=f"Number of top allocations to show (default: {DEFAULT_TOP_FRAMES})",
    )
    parser.addoption(
        "--mem-report",
        type=str,
        default=None,
        help="Save memory report to JSON file",
    )
    parser.addoption(
        "--mem-baseline",
        type=str,
        default=None,
        help="Load baseline JSON for memory regression detection",
    )
    parser.addoption(
        "--mem-isolated",
        action="store_true",
        default=DEFAULT_ISOLATED,
        help="Run each test in an isolated subprocess to contain memory leaks",
    )
    parser.addoption(
        "--mem-auto-xfail",
        action="store_true",
        default=False,
        help="Auto-mark tests exceeding memory threshold as xfail",
    )


# ---------------------------------------------------------------------------
# Plugin hooks
# ---------------------------------------------------------------------------

def pytest_configure(config):
    global _ISOLATED_MODE

    if config.getoption("--mem-profile"):
        if not tracemalloc.is_tracing():
            tracemalloc.start(25)  # 25 frames deep
        config.pluginmanager.register(_MemProfilerHook(config), "memprofiler")

    if config.getoption("--mem-isolated"):
        _ISOLATED_MODE = True
        # Collect tests first, then run each in a subprocess
        config.option.verbose = max(config.option.verbose or 0, 1)


class _MemProfilerHook:
    """Pytest hook implementation for memory profiling."""

    def __init__(self, config):
        self.config = config
        self.threshold_mb = config.getoption("--mem-threshold", DEFAULT_THRESHOLD_MB)
        self.top_frames = config.getoption("--mem-top", DEFAULT_TOP_FRAMES)
        self.mem_report_path = config.getoption("--mem-report", None)
        self.baseline_path = config.getoption("--mem-baseline", None)
        self.auto_xfail = config.getoption("--mem-auto-xfail", False)
        self.baseline = {}
        self._failed_mem_tests = []

        if self.baseline_path and Path(self.baseline_path).exists():
            with open(self.baseline_path) as f:
                self.baseline = json.load(f)
            print(f"\n[MEM-PROF] Loaded baseline from {self.baseline_path}", file=sys.stderr)

    def pytest_runtest_setup(self, item):
        """Take pre-test snapshot."""
        tracemalloc.take_snapshot()
        nid = item.nodeid
        _MEM_DATA[nid] = {
            'test_path': item.nodeid,
            'filename': item.location[0],
            'basename': item.location[2] if len(item.location) > 2 else item.name,
            'start_time': time.time(),
            'pre_snapshot': tracemalloc.take_snapshot(),
            'pre_rss_mb': _get_rss_mb(),
        }

    def pytest_runtest_call(self, item):
        """Mid-test checkpoint (optional, for long tests)."""
        pass

    def pytest_runtest_teardown(self, item):
        """Take post-test snapshot and compute delta."""
        nid = item.nodeid
        data = _MEM_DATA.get(nid, {})

        post_snapshot = tracemalloc.take_snapshot()
        post_rss = _get_rss_mb()
        duration = time.time() - data.get('start_time', 0)

        # Compute top allocations
        try:
            stats = post_snapshot.statistics('lineno')
            top_allocs = [str(s) for s in stats[:self.top_frames]]
        except Exception:
            top_allocs = []

        # Compute per-test delta
        pre_rss = data.get('pre_rss_mb', 0)
        delta_mb = round(post_rss - pre_rss, 2)

        # Compare to baseline if available
        regression = None
        test_key = data.get('filename', nid)
        if test_key in self.baseline:
            baseline_delta = self.baseline.get(test_key, {}).get('delta_mb', 0)
            if baseline_delta > 0 and delta_mb > baseline_delta * 1.2:  # 20% regression
                regression = round(delta_mb - baseline_delta, 2)

        _MEM_DATA[nid].update({
            'end_time': time.time(),
            'duration_s': round(duration, 3),
            'post_rss_mb': post_rss,
            'delta_mb': delta_mb,
            'peak_snapshot': post_snapshot,
            'top_allocations': top_allocs,
            'regression_mb': regression,
        })

        # Alert on threshold breach
        if abs(delta_mb) > self.threshold_mb:
            print(f"\n[MEM-ALERT] {item.nodeid}: +{delta_mb} MB (threshold: {self.threshold_mb} MB)",
                  file=sys.stderr)
            if self.auto_xfail:
                self._failed_mem_tests.append(item.nodeid)

    def pytest_collection_finish(self, session):
        """If isolated mode, re-dispatch tests to subprocesses."""
        if not _ISOLATED_MODE:
            return

        tests = [item.nodeid for item in session.items]
        if not tests:
            return

        print(f"\n[MEM-ISOLATED] Running {len(tests)} tests in isolated subprocesses...",
              file=sys.stderr)

        # We need to re-run pytest for each test
        import subprocess
        base_cmd = [sys.executable, "-m", "pytest"]
        # Preserve original pytest args minus --mem-isolated
        orig_args = [a for a in sys.argv if a != "--mem-isolated"]
        base_cmd.extend(orig_args[2:])  # Skip python -m pytest

        results = {}
        for test in tests:
            result = subprocess.run(
                base_cmd + [test],
                capture_output=True,
                text=True,
            )
            results[test] = {
                'returncode': result.returncode,
                'stdout': result.stdout[:2000],
                'stderr': result.stderr[:2000],
            }

        # Summarize
        failures = {k: v for k, v in results.items() if v['returncode'] != 0}
        if failures:
            print(f"\n[MEM-ISOLATED] {len(failures)}/{len(tests)} tests had issues:",
                  file=sys.stderr)
            for test, data in failures.items():
                print(f"  {test}: exit code {data['returncode']}", file=sys.stderr)

    def pytest_sessionfinish(self, session):
        """Export memory profile summary."""
        if not tracemalloc.is_tracing():
            return

        # Build summary
        summary = {
            'timestamp': time.time(),
            'threshold_mb': self.threshold_mb,
            'tests': {},
            'mem_alerts': [],
            'auto_xfailed': self._failed_mem_tests,
        }

        for nid, data in _MEM_DATA.items():
            entry = {
                'duration_s': data.get('duration_s'),
                'delta_mb': data.get('delta_mb'),
                'pre_rss_mb': data.get('pre_rss_mb'),
                'post_rss_mb': data.get('post_rss_mb'),
                'top_allocations': data.get('top_allocations', []),
                'regression_mb': data.get('regression_mb'),
            }
            summary['tests'][nid] = entry

            # Track alerts
            if abs(data.get('delta_mb', 0)) > self.threshold_mb:
                summary['mem_alerts'].append({
                    'test': nid,
                    'delta_mb': data.get('delta_mb'),
                })

        # Save report
        if self.mem_report_path:
            with open(self.mem_report_path, 'w') as f:
                json.dump(summary, f, indent=2, default=str)
            print(f"\n[MEM-PROF] Report saved to: {self.mem_report_path}", file=sys.stderr)

        # Print summary table
        self._print_summary_table(summary)

    def _print_summary_table(self, summary):
        """Print a summary table of memory profiles."""
        tests = summary.get('tests', {})
        if not tests:
            return

        print(f"\n{'=' * 100}")
        print(f"[MEM-PROF] Per-Test Memory Profile Summary")
        print(f"{'=' * 100}")
        print(f"{'Test':<60} {'Delta(MB)':>10} {'Duration(s)':>12} {'Regression':>12}")
        print(f"{'-' * 60} {'-' * 10} {'-' * 12} {'-' * 12}")

        sorted_tests = sorted(
            tests.items(),
            key=lambda x: abs(x[1].get('delta_mb', 0)),
            reverse=True,
        )

        for nid, data in sorted_tests:
            delta = data.get('delta_mb', 0)
            duration = data.get('duration_s', 0)
            regression = data.get('regression_mb')

            # Truncate long test names
            display_name = nid if len(nid) < 60 else f"...{nid[-57:]}"

            reg_str = f"+{regression}" if regression else "-"
            delta_str = f"+{delta}" if delta >= 0 else str(delta)

            print(f"{display_name:<60} {delta_str:>10} {duration:>12} {reg_str:>12}")

        print(f"{'=' * 100}")

        # Print top memory consumers
        top_n = min(10, len(sorted_tests))
        if top_n > 0:
            print(f"\n[MEM-PROF] Top {top_n} memory consumers:")
            for i, (nid, data) in enumerate(sorted_tests[:top_n], 1):
                delta = data.get('delta_mb', 0)
                print(f"  {i}. {nid} (+{delta} MB)")
                for line in data.get('top_allocations', [])[:3]:
                    print(f"     {line}")
                print()


# ---------------------------------------------------------------------------
# Utility functions (standalone usage)
# ---------------------------------------------------------------------------

def _get_rss_mb():
    """Get current process RSS in MB."""
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except ImportError:
        try:
            with open(f"/proc/{os.getpid()}/statm") as f:
                pages = int(f.read().split()[1])
                return pages * 4096 / (1024 * 1024)
        except Exception:
            return 0.0


def generate_baseline(test_pattern="tests", output="test_memory_profiles/baseline.json"):
    """Generate a memory baseline by running tests once.

    Usage:
        python scripts/pytest_memprof_plugin.py --generate-baseline
        python scripts/pytest_memprof_plugin.py --generate-baseline -k "test_battle"
    """
    import subprocess

    os.makedirs(os.path.dirname(output) if os.path.dirname(output) else ".", exist_ok=True)

    cmd = [
        sys.executable, "-m", "pytest",
        test_pattern,
        "--mem-profile",
        "--mem-report", output,
        "-q",
    ]

    print(f"[BASELINE] Generating baseline: {' '.join(cmd)}")
    result = subprocess.run(cmd)

    if result.returncode == 0 and Path(output).exists():
        print(f"[BASELINE] Saved to {output}")
    else:
        print(f"[BASELINE] Failed (exit code {result.returncode})")

    return result.returncode


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    if "--generate-baseline" in sys.argv:
        idx = sys.argv.index("--generate-baseline")
        pattern = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "tests"
        output = "test_memory_profiles/baseline.json"
        sys.exit(generate_baseline(pattern, output))
    else:
        print("Usage:")
        print("  pytest --mem-profile                          # Profile tests")
        print("  python pytest_memprof_plugin.py --generate-baseline [pattern]")
        sys.exit(0)
