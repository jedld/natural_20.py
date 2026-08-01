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
import importlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_LIMIT_MB = 1024  # Kill a test process tree at 1GB RSS
DEFAULT_TOP_N = 20
DEFAULT_BATCH_SIZE = 5  # Group this many sequential results in console output
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_SAMPLE_INTERVAL = 0.1


def get_system_memory_mb():
    """Get total system memory in MB."""
    try:
        psutil = importlib.import_module("psutil")
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


def collect_test_list(test_paths, extra_args=None, granularity="test"):
    """Collect list of test IDs using pytest --collect-only."""
    if granularity == "suite":
        return test_paths

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
    if granularity == "file":
        # Keep collection order while running each file only once. A file-level
        # sweep is much faster than starting pytest once for every test case.
        return list(dict.fromkeys(test_id.split("::", 1)[0] for test_id in tests))
    return tests


def _set_address_space_limit(limit_mb):
    """Apply a last-resort allocation ceiling before the child starts.

    RSS monitoring is the primary limit. RLIMIT_AS is deliberately larger so
    normal shared-library mappings are not mistaken for resident memory while
    still preventing a single allocation from outrunning the monitor.
    """
    import resource

    # Threads and memory-mapped libraries reserve substantially more virtual
    # address space than resident memory. Keep this emergency ceiling well
    # above the monitored RSS cap to avoid low-RSS "can't start new thread"
    # failures while still bounding allocations that outrun the sampler.
    address_space_mb = max(limit_mb * 8, limit_mb + 7168)
    limit_bytes = address_space_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))


def _process_tree_rss_mb(proc):
    """Return resident memory for a process and all accessible descendants."""
    psutil = importlib.import_module("psutil")
    try:
        root = psutil.Process(proc.pid)
        processes = [root, *root.children(recursive=True)]
        return sum(
            child.memory_info().rss
            for child in processes
            if child.is_running()
        ) / (1024 * 1024)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return 0.0


def _kill_process_group(proc):
    """Terminate the whole pytest process group, including leaked children."""
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=2)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _drain_output(stream, chunks):
    """Continuously drain child output while retaining only the latest 64 KiB."""
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        stream.close()


def run_single_test(
    test_id,
    limit_mb=DEFAULT_LIMIT_MB,
    timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
    sample_interval=DEFAULT_SAMPLE_INTERVAL,
    fail_fast=True,
    extra_args=None,
):
    """Run one test node or file with bounded process-tree memory."""
    start_time = time.time()

    # Run test in subprocess
    cmd = [
        sys.executable, "-m", "pytest",
        test_id,
        "-v", "--tb=short",
        "--capture=no",
        "--no-header", "-q",
    ]
    if fail_fast:
        cmd.append("-x")
    if extra_args:
        cmd.extend(extra_args)

    peak_rss_mb = 0.0
    timed_out = False
    memory_limited = False
    output_chunks = deque(maxlen=16)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
        preexec_fn=lambda: _set_address_space_limit(limit_mb),
    )
    output_thread = threading.Thread(
        target=_drain_output,
        args=(proc.stdout, output_chunks),
        daemon=True,
    )
    output_thread.start()
    while proc.poll() is None:
        current_rss_mb = _process_tree_rss_mb(proc)
        peak_rss_mb = max(peak_rss_mb, current_rss_mb)
        elapsed = time.time() - start_time
        if current_rss_mb > limit_mb:
            memory_limited = True
            _kill_process_group(proc)
            break
        if elapsed > timeout_seconds:
            timed_out = True
            _kill_process_group(proc)
            break
        time.sleep(sample_interval)

    rc = proc.wait()
    output_thread.join(timeout=2)
    combined_output = "".join(output_chunks)

    # RLIMIT_AS covers reserved virtual memory (including thread stacks and
    # mapped libraries), so report it separately from an observed RSS breach.
    address_space_limited = "MemoryError" in combined_output and not memory_limited

    duration = time.time() - start_time

    return {
        "test_id": test_id,
        "returncode": rc,
        "duration_s": round(duration, 3),
        "peak_rss_mb": round(peak_rss_mb, 2),
        "memory_limited": memory_limited,
        "address_space_limited": address_space_limited,
        "timeout": timed_out,
        "error_summary": _summarize_error(combined_output),
        "output_tail": combined_output[-65536:],
    }


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


def run_batch(tests, limit_mb, timeout_seconds, sample_interval, fail_fast, extra_args=None):
    """Run a display batch sequentially, with each item in a fresh process."""
    results = {}

    # Sequential execution ensures the configured limit is the maximum extra
    # memory this runner can place under pressure at any one time.
    for test_id in tests:
        result = run_single_test(
            test_id,
            limit_mb,
            timeout_seconds,
            sample_interval,
            fail_fast,
            extra_args,
        )
        results[test_id] = result

        status = "PASS" if result["returncode"] == 0 else "FAIL"
        print(f"  [{status}] {test_id} ({result['duration_s']}s, peak={result['peak_rss_mb']}MB)")

        if result["timeout"]:
            print(f"    TIMEOUT (>{timeout_seconds}s)")
        if result["memory_limited"]:
            print(f"    MEMORY LIMIT EXCEEDED ({limit_mb}MB)")

    return results


def generate_report(all_results, report_path, top_n=DEFAULT_TOP_N):
    """Generate memory report sorted by memory consumption."""
    # Every item runs in a fresh process, so peak RSS is comparable across tests.
    sorted_results = sorted(
        all_results.values(),
        key=lambda r: r.get("peak_rss_mb", 0),
        reverse=True,
    )

    report = {
        "timestamp": datetime.now().isoformat(),
        "system_memory_mb": round(get_system_memory_mb(), 2),
        "total_tests": len(all_results),
        "passed": sum(1 for r in all_results.values() if r["returncode"] == 0),
        "failed": sum(1 for r in all_results.values() if r["returncode"] != 0),
        "timeouts": sum(1 for r in all_results.values() if r["timeout"]),
        "memory_limited": sum(1 for r in all_results.values() if r["memory_limited"]),
        "address_space_limited": sum(1 for r in all_results.values() if r.get("address_space_limited")),
        "summary": {
            "max_peak_rss_mb": sorted_results[0]["peak_rss_mb"] if sorted_results else 0,
            "min_peak_rss_mb": sorted_results[-1]["peak_rss_mb"] if sorted_results else 0,
            "avg_peak_rss_mb": round(
                sum(r.get("peak_rss_mb", 0) for r in sorted_results) / len(sorted_results), 2
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
    print(f"Memory-limited:{report['memory_limited']:>7}")
    print(f"Address-space limited:{report['address_space_limited']:>3}")
    print(f"{'='*80}")

    print(f"\nTop {min(top_n, len(report['all_results']))} Memory Consumers:")
    print(f"{'Test':<60} {'Peak(MB)':>10} {'Status':>8} {'Time(s)':>8}")
    print(f"{'-'*60} {'-'*10} {'-'*8} {'-'*8}")

    for i, result in enumerate(report["top_memory_consumers"][:top_n], 1):
        test = result["test_id"]
        peak = result.get("peak_rss_mb", 0)
        status = "PASS" if result["returncode"] == 0 else "FAIL"
        duration = result.get("duration_s", 0)

        # Truncate long test names
        if len(test) > 60:
            test = f"...{test[-57:]}"

        print(f"{test:<60} {peak:>10.2f} {status:>8} {duration:>8.2f}")

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
            reason = " (TIMEOUT)" if result["timeout"] else ""
            if result["memory_limited"]:
                reason = " (MEMORY LIMIT)"
            elif result.get("address_space_limited"):
                reason += " (ADDRESS-SPACE LIMIT)"
            print(f"  FAIL: {test} (exit={rc}, time={duration:.1f}s){reason}")
            for err in result.get("error_summary", [])[:2]:
                print(f"        {err}")


def main():
    parser = argparse.ArgumentParser(description="Diagnose memory-hungry tests")
    parser.add_argument("test_paths", nargs="*", default=["."], help="Test files/directories")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N, help=f"Show top N consumers (default: {DEFAULT_TOP_N})")
    parser.add_argument("--limit-mb", type=int, default=DEFAULT_LIMIT_MB, help=f"Memory limit per subprocess (default: {DEFAULT_LIMIT_MB})")
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH_SIZE, help=f"Sequential results per console group (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help=f"Timeout per test/file in seconds (default: {DEFAULT_TIMEOUT_SECONDS})")
    parser.add_argument("--sample-interval", type=float, default=DEFAULT_SAMPLE_INTERVAL, help=f"RSS sampling interval in seconds (default: {DEFAULT_SAMPLE_INTERVAL})")
    parser.add_argument(
        "--granularity",
        choices=("suite", "file", "test"),
        default="test",
        help=(
            "Run the whole selected suite once to catch cumulative growth, one "
            "subprocess per file for a fast sweep, or one per test for precise isolation"
        ),
    )
    parser.add_argument("--report", type=str, default=None, help="Save report to JSON file")
    parser.add_argument("-k", type=str, default=None, help="Keyword filter for tests")
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Run pytest with this many xdist workers (0 keeps serial execution)",
    )

    args = parser.parse_args()

    try:
        importlib.import_module("psutil")
    except ImportError:
        parser.error("psutil is required for safe process-tree memory enforcement; install requirements.txt")

    print(f"[INFO] Collecting test list...")
    print(f"[INFO] System memory: {get_system_memory_mb() / 1024:.1f} GB")
    print(f"[INFO] Memory limit per test: {args.limit_mb} MB")

    extra_args = []
    if args.k:
        extra_args.extend(["-k", args.k])
    if args.workers > 0:
        extra_args.extend(["-n", str(args.workers)])

    test_list = collect_test_list(args.test_paths, extra_args, args.granularity)
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
        batch_results = run_batch(
            batch,
            args.limit_mb,
            args.timeout,
            args.sample_interval,
            fail_fast=args.granularity != "suite",
            extra_args=extra_args,
        )
        all_results.update(batch_results)

    elapsed = time.time() - overall_start
    print(f"\n[DONE] All batches completed in {elapsed:.1f}s")

    # Generate and print report
    report = generate_report(all_results, args.report, args.top)
    print_report(report, args.top)

    # Suggest fixes
    top_consumers = report["top_memory_consumers"][:3]
    for result in top_consumers:
        if result.get("peak_rss_mb", 0) > 200:
            test = result["test_id"]
            print(f"\n[SUSPECT] {test} (peak {result['peak_rss_mb']}MB)")
            print(f"  This test may have a memory leak or heavy setup.")
            print(f"  Suggested actions:")
            print(f"    1. Run in isolation: pytest {test} -v --tb=long")
            print(f"    2. Profile with tracemalloc: pytest {test} --mem-profile")
            print(f"    3. Check for large fixture loading or unclosed resources")

    exit_code = 1 if report["failed"] > 0 or report["timeouts"] > 0 else 0
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
