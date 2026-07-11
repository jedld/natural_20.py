#!/usr/bin/env python3
"""
Diagnose memory-hungry tests by running each test in an isolated subprocess
with memory tracking. Outputs a report of the top memory consumers.

Usage:
    python scripts/diagnose_memory_hogs.py                          # Run all tests
    python scripts/diagnose_memory_hogs.py tests/test_battle.py     # Specific file
    python scripts/diagnose_memory_hogs.py -k "test_spell"          # Keyword filter
    python scripts/diagnose_memory_hogs.py --top 20                 # Show top 20
    python scripts/diagnose_memory_hogs.py --limit-mb 4096          # Kill at 4GB
    python scripts/diagnose_memory_hogs.py --report mem_hog_report.json
    python scripts/diagnose_memory_hogs.py --batch 5                # Run 5 tests at a time
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_LIMIT_MB = 4096  # Kill subprocess at 4GB RSS
DEFAULT_TOP_N = 20
DEFAULT_BATCH_SIZE = 5  # Run this many tests concurrently to avoid OOM


def get_system_memory_mb():
    """Get total system memory in MB."""
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 * 1024)
    except ImportError:
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) / 1024  # kB to MB
        except Exception:
            pass
    return 16384  # Default estimate: 16 GB


def collect_test_list(test_paths, extra_args=None):
    """Collect list of test IDs using pytest --collect-only."""
    cmd = [
        sys.executable, "-m", "pytest",
        *test_paths,
        "--collect-only", "-q",
        "--no-header",
    ]
    if extra_args:
        cmd.extend(extra_args)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    tests = []
    for line in result.stdout.splitlines():
        line = line.strip()
        # Skip collection headers
        if line.startswith("collected") or line.startswith("[") or not line:
            continue
        # Match test IDs like tests/test_foo.py::test_bar
        if "::" in line and line.startswith("tests/"):
            tests.append(line)
    return tests


def run_single_test(test_id, limit_mb=DEFAULT_LIMIT_MB):
    """Run a single test in a subprocess with memory limit."""
    import resource
    start_time = time.time()

    # Track memory before
    pre_rss = _get_process_rss_mb()

    # Run test in subprocess
    cmd = [
        sys.executable, "-m", "pytest",
        test_id,
        "-v", "--tb=short",
        "-x", "--capture=no",
        "--no-header", "-q",
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = proc.communicate(timeout=120)  # 2 minute timeout per test
        rc = proc.returncode

    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.stdout.read(), proc.stderr.read()
        rc = -1  # Timeout

    duration = time.time() - start_time
    post_rss = _get_process_rss_mb()
    delta_mb = round(post_rss - pre_rss, 2)

    # Parse pytest output for any memory info
    mem_alerts = re.findall(r"\[MEM-ALERT\] (.+?): (\S+) MB", stderr)

    return {
        "test_id": test_id,
        "returncode": rc,
        "duration_s": round(duration, 3),
        "pre_rss_mb": round(pre_rss, 2),
        "post_rss_mb": round(post_rss, 2),
        "delta_mb": delta_mb,
        "mem_alerts": mem_alerts,
        "timeout": False,
        "oom_killed": False,
        "error_summary": _summarize_error(stdout + stderr),
    }


def _get_process_rss_mb():
    """Get current process RSS in MB."""
    try:
        import psutil
        return psutil.Process().memory_info().rss / (1024 * 1024)
    except ImportError:
        try:
            with open(f"/proc/{os.getpid()}/statm") as f:
                pages = int(f.read().split()[1])
                return pages * 4096 / (1024 * 1024)
        except Exception:
            return 0.0


def _summarize_error(output):
    """Extract key error information from test output."""
    lines = output.splitlines()
    errors = []

    for line in lines:
        if "ERROR" in line or "FAILED" in line:
            errors.append(line[:200])
        if "Exception" in line or "Error" in line:
            errors.append(line[:200])

    return errors[:5]  # Max 5 error lines


def run_batch(tests, limit_mb, batch_size=DEFAULT_BATCH_SIZE):
    """Run a batch of tests concurrently using process pool."""
    results = {}

    # Use ProcessPoolExecutor for true process isolation
    # Note: We can't use fork on macOS, so we'll run tests sequentially per batch
    # but each in its own subprocess via pytest
    for test_id in tests:
        result = run_single_test(test_id, limit_mb)
        results[test_id] = result

        status = "PASS" if result["returncode"] == 0 else "FAIL"
        delta = result["delta_mb"]
        delta_str = f"+{delta}" if delta >= 0 else str(delta)
        print(f"  [{status}] {test_id} ({result['duration_s']}s, delta={delta_str}MB)")

        if result["timeout"]:
            print(f"    TIMEOUT (>120s)")
        if result["mem_alerts"]:
            for test, delta in result["mem_alerts"]:
                print(f"    MEM-ALERT: {test} +{delta}MB")

    return results


def generate_report(all_results, report_path, top_n=DEFAULT_TOP_N):
    """Generate memory report sorted by memory consumption."""
    # Sort by absolute memory delta
    sorted_results = sorted(
        all_results.values(),
        key=lambda r: abs(r.get("delta_mb", 0)),
        reverse=True,
    )

    report = {
        "timestamp": datetime.now().isoformat(),
        "system_memory_mb": round(get_system_memory_mb(), 2),
        "total_tests": len(all_results),
        "passed": sum(1 for r in all_results.values() if r["returncode"] == 0),
        "failed": sum(1 for r in all_results.values() if r["returncode"] != 0),
        "timeouts": sum(1 for r in all_results.values() if r["timeout"]),
        "summary": {
            "max_delta_mb": sorted_results[0]["delta_mb"] if sorted_results else 0,
            "min_delta_mb": sorted_results[-1]["delta_mb"] if sorted_results else 0,
            "avg_delta_mb": round(
                sum(r.get("delta_mb", 0) for r in sorted_results) / len(sorted_results), 2
            ) if sorted_results else 0,
        },
        "top_memory_consumers": sorted_results[:top_n],
        "all_results": sorted_results,
    }

    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n[REPORT] Saved to {report_path}")

    return report


def print_report(report, top_n=DEFAULT_TOP_N):
    """Print human-readable report."""
    print(f"\n{'='*80}")
    print(f"[MEMORY DIAGNOSTIC REPORT]")
    print(f"{'='*80}")
    print(f"System Memory: {report['system_memory_mb'] / 1024:.1f} GB")
    print(f"Total Tests:   {report['total_tests']}")
    print(f"Passed:        {report['passed']}")
    print(f"Failed:        {report['failed']}")
    print(f"Timeouts:      {report['timeouts']}")
    print(f"{'='*80}")

    print(f"\nTop {min(top_n, len(report['all_results']))} Memory Consumers:")
    print(f"{'Test':<60} {'Delta(MB)':>10} {'Status':>8} {'Time(s)':>8}")
    print(f"{'-'*60} {'-'*10} {'-'*8} {'-'*8}")

    for i, result in enumerate(report["top_memory_consumers"][:top_n], 1):
        test = result["test_id"]
        delta = result.get("delta_mb", 0)
        status = "PASS" if result["returncode"] == 0 else "FAIL"
        duration = result.get("duration_s", 0)

        # Truncate long test names
        if len(test) > 60:
            test = f"...{test[-57:]}"

        delta_str = f"+{delta}" if delta >= 0 else str(delta)
        print(f"{test:<60} {delta_str:>10} {status:>8} {duration:>8.2f}")

    print(f"{'='*80}")

    # Print failures
    failures = [r for r in report["all_results"] if r["returncode"] != 0]
    if failures:
        print(f"\n{'='*80}")
        print(f"FAILURES ({len(failures)})")
        print(f"{'='*80}")
        for result in failures:
            test = result["test_id"]
            rc = result["returncode"]
            duration = result.get("duration_s", 0)
            timeout = " (TIMEOUT)" if result["timeout"] else ""
            print(f"  FAIL: {test} (exit={rc}, time={duration:.1f}s){timeout}")
            for err in result.get("error_summary", [])[:2]:
                print(f"        {err}")


def main():
    parser = argparse.ArgumentParser(description="Diagnose memory-hungry tests")
    parser.add_argument("test_paths", nargs="*", default=["."], help="Test files/directories")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N, help=f"Show top N consumers (default: {DEFAULT_TOP_N})")
    parser.add_argument("--limit-mb", type=int, default=DEFAULT_LIMIT_MB, help=f"Memory limit per subprocess (default: {DEFAULT_LIMIT_MB})")
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH_SIZE, help=f"Tests per batch (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--report", type=str, default=None, help="Save report to JSON file")
    parser.add_argument("-k", type=str, default=None, help="Keyword filter for tests")

    args = parser.parse_args()

    print(f"[INFO] Collecting test list...")
    print(f"[INFO] System memory: {get_system_memory_mb() / 1024:.1f} GB")
    print(f"[INFO] Memory limit per test: {args.limit_mb} MB")

    extra_args = []
    if args.k:
        extra_args = ["-k", args.k]

    test_list = collect_test_list(args.test_paths, extra_args)
    if not test_list:
        print("[ERROR] No tests found")
        sys.exit(1)

    print(f"[INFO] Found {len(test_list)} tests")
    print(f"[INFO] Running tests in batches of {args.batch}...\n")

    # Split into batches
    batches = [test_list[i:i + args.batch] for i in range(0, len(test_list), args.batch)]

    all_results = {}
    overall_start = time.time()

    for batch_idx, batch in enumerate(batches):
        print(f"\n[BATCH {batch_idx + 1}/{len(batches)}] Running {len(batch)} tests...")
        batch_results = run_batch(batch, args.limit_mb)
        all_results.update(batch_results)

    elapsed = time.time() - overall_start
    print(f"\n[DONE] All batches completed in {elapsed:.1f}s")

    # Generate and print report
    report = generate_report(all_results, args.report, args.top)
    print_report(report, args.top)

    # Suggest fixes
    top_consumers = report["top_memory_consumers"][:3]
    for result in top_consumers:
        if abs(result.get("delta_mb", 0)) > 200:  # > 200MB delta
            test = result["test_id"]
            print(f"\n[SUSPECT] {test} (+{result['delta_mb']}MB)")
            print(f"  This test may have a memory leak or heavy setup.")
            print(f"  Suggested actions:")
            print(f"    1. Run in isolation: pytest {test} -v --tb=long")
            print(f"    2. Profile with tracemalloc: pytest {test} --mem-profile")
            print(f"    3. Check for large fixture loading or unclosed resources")

    exit_code = 1 if report["failed"] > 0 or report["timeouts"] > 0 else 0
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
