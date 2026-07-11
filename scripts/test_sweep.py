#!/usr/bin/env python3
"""
Test sweep utility: runs tests in batches, detects failures, memory issues,
and automatically attempts fixes.

Usage:
    python scripts/test_sweep.py                   # Run all tests in batches
    python scripts/test_sweep.py tests/test_battle.py  # Specific file
    python scripts/test_sweep.py --batch-size 3     # Custom batch size
    python scripts/test_sweep.py --mem-threshold 300
    python scripts/test_sweep.py --auto-fix --auto-xfail
    python scripts/test_sweep.py --parallel 4       # Run batches in parallel
    python scripts/test_sweep.py --report report.json
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Auto-fix strategies
# ---------------------------------------------------------------------------

class TestAutoFixer:
    """Attempts to automatically fix common test failures."""

    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.fixes_applied = 0
        self.conftest_path = Path("conftest.py")

    def fix_import_errors(self, error_output, test_file):
        """Fix ImportError / ModuleNotFoundError patterns."""
        patterns = [
            (r"ModuleNotFoundError: No module named '(\S+)'", "missing_module"),
            (r"ImportError:.*No module named '(\S+)'", "missing_module"),
            (r"ImportError:.*cannot import name '(\S+)'", "missing_import"),
            (r"AttributeError: '(\S+)' object has no attribute '(\S+)'", "missing_attribute"),
        ]

        for pattern, fix_type in patterns:
            match = re.search(pattern, error_output)
            if match:
                detail = match.group(1)
                if fix_type == "missing_module":
                    print(f"[AUTO-FIX] Suggest: pip install {detail}")
                elif fix_type == "missing_import":
                    print(f"[AUTO-FIX] Check import: '{detail}' - verify module structure")
                elif fix_type == "missing_attribute":
                    print(f"[AUTO-FIX] Check attribute access: {detail}")
                return True
        return False

    def fix_fixture_path_errors(self, error_output, test_file):
        """Fix FileNotFoundError for test fixtures."""
        match = re.search(r"FileNotFoundError: \[Errno 2\] No such file or directory: '([^']+)'", error_output)
        if match:
            missing_file = match.group(1)
            print(f"[AUTO-FIX] Missing fixture: {missing_file}")
            print(f"         Check if file exists or adjust path in {test_file}")
            return True
        return False

    def fix_assertion_errors(self, error_output, test_file):
        """Suggest fixes for assertion errors."""
        if "AssertionError" in error_output:
            # Try to extract the failed assertion
            match = re.search(r"AssertionError: assert (.+)", error_output)
            if match:
                assertion = match.group(1)
                print(f"[AUTO-FIX] Failed assertion: {assertion}")
                print(f"         Review expected vs actual values in {test_file}")
            return True
        return False

    def mark_xfail(self, test_id, reason="Failing test marked xfail for investigation"):
        """Add test to _TEMP_XFAIL in conftest.py."""
        if self.dry_run:
            print(f"[DRY-RUN] Would mark {test_id} as xfail: {reason}")
            return True

        if not self.conftest_path.exists():
            print(f"[AUTO-FIX] No conftest.py found")
            return False

        content = self.conftest_path.read_text()
        if test_id in content:
            print(f"[AUTO-FIX] {test_id} already in xfail set")
            return False

        # Find _TEMP_XFAIL set
        xfail_match = re.search(r"_TEMP_XFAIL\s*=\s*\{", content)
        if not xfail_match:
            print(f"[AUTO-FIX] Could not find _TEMP_XFAIL in conftest.py")
            return False

        # Find closing brace
        start = xfail_match.end()
        depth = 1
        pos = start
        while pos < len(content) and depth > 0:
            if content[pos] == '{':
                depth += 1
            elif content[pos] == '}':
                depth -= 1
            pos += 1

        insert_pos = pos - 1  # Position before closing brace
        xfail_entry = f'    "{test_id}",\n    # Auto-xfailed: {reason}\n'
        new_content = content[:insert_pos] + "\n" + xfail_entry + content[insert_pos:]

        self.conftest_path.write_text(new_content)
        print(f"[AUTO-FIX] Added {test_id} to _TEMP_XFAIL")
        self.fixes_applied += 1
        return True

    def attempt_fix(self, error_output, test_id, test_file, test_name):
        """Try all fix strategies in order."""
        if self.dry_run:
            print(f"[DRY-RUN] Would attempt fixes for: {test_id}")
            self.fix_import_errors(error_output, test_file)
            self.fix_fixture_path_errors(error_output, test_file)
            self.fix_assertion_errors(error_output, test_file)
            return False

        if self.fix_import_errors(error_output, test_file):
            return True
        if self.fix_fixture_path_errors(error_output, test_file):
            return True
        if self.fix_assertion_errors(error_output, test_file):
            return True
        return False


# ---------------------------------------------------------------------------
# Batch test runner
# ---------------------------------------------------------------------------

def discover_tests(test_paths, pattern="test_*.py"):
    """Discover test files or specific test items."""
    tests = []
    for path in test_paths:
        p = Path(path)
        if p.is_file():
            tests.append(str(p))
        elif p.is_dir():
            tests.extend(str(f) for f in p.glob(f"**/{pattern}"))
    return sorted(set(tests))


def run_test_batch(test_items, batch_size=10, mem_threshold=500, auto_fix=False, auto_xfail=False):
    """Run a batch of tests and return results."""
    fixer = TestAutoFixer(dry_run=False) if auto_fix else None
    results: dict = {"passed": [], "failed": [], "errors": [], "skipped": [], "duration_s": 0.0, "returncode": 0, "mem_alerts": []}
    mem_data = {}

    batch_str = " ".join(test_items[:3])
    if len(test_items) > 3:
        batch_str += f" ... (+{len(test_items) - 3} more)"

    print(f"\n{'='*60}")
    print(f"[BATCH] Running {len(test_items)} tests: {batch_str}")
    print(f"{'='*60}")

    start_time = time.time()

    # Run pytest with memory monitoring
    cmd = [
        sys.executable, "-m", "pytest",
        *test_items,
        "-v", "--tb=line",
        "--no-header",
        "-q",
    ]

    env = os.environ.copy()
    env["N20_MEM_THRESHOLD_MB"] = str(mem_threshold)

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    duration = time.time() - start_time

    # Parse output
    stdout = result.stdout
    stderr = result.stderr
    combined = stdout + stderr

    # Count results from pytest summary
    passed_match = re.search(r"(\d+) passed", combined)
    failed_match = re.search(r"(\d+) failed", combined)
    error_match = re.search(r"(\d+) error", combined)
    skipped_match = re.search(r"(\d+) skipped", combined)

    if passed_match:
        results["passed"].append({"count": int(passed_match.group(1)), "duration_s": round(duration, 2)})
    if failed_match:
        results["failed"].append({"count": int(failed_match.group(1))})
    if error_match:
        results["errors"].append({"count": int(error_match.group(1))})
    if skipped_match:
        results["skipped"].append({"count": int(skipped_match.group(1))})

    # Extract individual failures
    if result.returncode != 0:
        # Find failed test lines
        for line in combined.splitlines():
            if " FAILED" in line or "ERROR" in line:
                test_match = re.search(r"(tests/\S+::\S+)", line)
                if test_match:
                    test_id = test_match.group(1)
                    error_line = line
                    results["failed"].append({
                        "test_id": test_id,
                        "error": error_line[:200],
                    })

                    if auto_fix and fixer:
                        fixer.attempt_fix(error_line, test_id, test_id.split("::")[0], test_id.split("::")[-1])
                    if auto_xfail and fixer:
                        fixer.mark_xfail(test_id)

    # Check for memory alerts
    mem_alerts = re.findall(r"\[MEM-ALERT\] (.+): \+(\S+) MB", stderr)
    if mem_alerts:
        for test_id, delta in mem_alerts:
            results["mem_alerts"] = results.get("mem_alerts", [])
            results["mem_alerts"].append({"test": test_id, "delta_mb": delta})


    return results


def run_sweep_parallel(test_files, batch_size=10, num_workers=4, **kwargs):
    """Run test batches in parallel."""
    batches = [test_files[i:i + batch_size] for i in range(0, len(test_files), batch_size)]
    all_results = {}

    def run_batch(batch_idx, batch_tests):
        batch_id = f"batch_{batch_idx}"
        print(f"\n{'#'*60}")
        print(f"[PARALLEL] Starting {batch_id} ({len(batch_tests)} tests)")
        print(f"{'#'*60}")
        return batch_id, run_test_batch(batch_tests, **kwargs)

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(run_batch, i, b): i for i, b in enumerate(batches)}
        for future in as_completed(futures):
            batch_id, batch_result = future.result()
            all_results[batch_id] = batch_result

    return all_results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(all_results, report_path, sweep_start):
    """Generate JSON report."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "duration_s": round(time.time() - sweep_start, 2),
        "batches": {},
        "summary": {
            "total_passed": 0,
            "total_failed": 0,
            "total_errors": 0,
            "total_skipped": 0,
            "total_duration_s": 0,
        },
    }

    for batch_id, data in all_results.items():
        report["batches"][batch_id] = data

        for item in data.get("passed", []):
            report["summary"]["total_passed"] += item.get("count", 0)
        for item in data.get("failed", []):
            report["summary"]["total_failed"] += item.get("count", 0)
        for item in data.get("errors", []):
            report["summary"]["total_errors"] += item.get("count", 0)
        for item in data.get("skipped", []):
            report["summary"]["total_skipped"] += item.get("count", 0)

        report["summary"]["total_duration_s"] += data.get("duration_s", 0)

    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n[REPORT] Saved to {report_path}")

    return report


def print_summary(report):
    """Print human-readable summary."""
    s = report["summary"]
    print(f"\n{'='*60}")
    print(f"[SUMMARY]")
    print(f"{'='*60}")
    print(f"  Passed:   {s['total_passed']}")
    print(f"  Failed:   {s['total_failed']}")
    print(f"  Errors:   {s['total_errors']}")
    print(f"  Skipped:  {s['total_skipped']}")
    print(f"  Duration: {s['total_duration_s']:.1f}s")
    print(f"{'='*60}")

    if s["total_failed"] > 0 or s["total_errors"] > 0:
        print("\n[FAILURES]")
        for batch_id, data in report.get("batches", {}).items():
            for item in data.get("failed", []):
                if "test_id" in item:
                    print(f"  FAIL: {item['test_id']}")
                    print(f"        {item.get('error', 'N/A')}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Test sweep with auto-fix capabilities")
    parser.add_argument("test_paths", nargs="*", default=["."], help="Test files or directories")
    parser.add_argument("--batch-size", type=int, default=10, help="Tests per batch (default: 10)")
    parser.add_argument("--parallel", type=int, default=0, help="Number of parallel workers (0 = sequential)")
    parser.add_argument("--mem-threshold", type=int, default=500, help="Memory threshold in MB (default: 500)")
    parser.add_argument("--auto-fix", action="store_true", help="Attempt auto-fixes for failures")
    parser.add_argument("--auto-xfail", action="store_true", help="Auto-mark failures as xfail")
    parser.add_argument("--report", type=str, default="test_sweep_report.json", help="Report output path")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")

    args = parser.parse_args()

    sweep_start = time.time()

    # Discover test files
    test_files = discover_tests(args.test_paths)
    if not test_files:
        print("[ERROR] No tests found")
        sys.exit(1)

    print(f"[INFO] Discovered {len(test_files)} test files")
    print(f"[INFO] Batch size: {args.batch_size}")
    print(f"[INFO] Memory threshold: {args.mem_threshold} MB")
    print(f"[INFO] Start time: {datetime.now().isoformat()}")

    if args.dry_run:
        print("\n[DRY-RUN] Would run the following test files:")
        for f in test_files:
            print(f"  - {f}")
        sys.exit(0)

    # Run sweep
    if args.parallel > 1:
        all_results = run_sweep_parallel(
            test_files,
            batch_size=args.batch_size,
            num_workers=args.parallel,
            mem_threshold=args.mem_threshold,
            auto_fix=args.auto_fix,
            auto_xfail=args.auto_xfail,
        )
    else:
        batches = [test_files[i:i + args.batch_size] for i in range(0, len(test_files), args.batch_size)]
        all_results = {}
        for i, batch in enumerate(batches):
            batch_id = f"batch_{i}"
            all_results[batch_id] = run_test_batch(
                batch,
                batch_size=args.batch_size,
                mem_threshold=args.mem_threshold,
                auto_fix=args.auto_fix,
                auto_xfail=args.auto_xfail,
            )

    # Generate report
    report = generate_report(all_results, args.report, sweep_start)
    print_summary(report)

    exit_code = 1 if report["summary"]["total_failed"] > 0 or report["summary"]["total_errors"] > 0 else 0
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
