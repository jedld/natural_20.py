#!/usr/bin/env python3
"""Bounded-memory leak harness for the n20-webapp test suite.

Runs the webapp suite in a SINGLE pytest process (no xdist) under
tracemalloc, sampling RSS and taking periodic allocation snapshots so
the per-test memory growth and the accumulating allocation sites can be
identified.

Usage:
    python scripts/webapp_mem_harness.py [extra pytest args...]

Environment:
    N20_HARNESS_SAMPLE  - take a tracemalloc snapshot every N tests (default 25)
    N20_HARNESS_CAP     - stop after this many tests (default 0 = all)
    N20_HARNESS_TOP     - frames per snapshot diff (default 15)
    N20_HARNESS_RSS_CAP - abort if RSS exceeds this many MB (default 0 = off)
"""
import gc
import os
import resource
import sys
import time
import tracemalloc
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (REPO, REPO / 'n20-webapp', REPO / 'n20-webapp' / 'webapp'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

SAMPLE_EVERY = int(os.environ.get('N20_HARNESS_SAMPLE', '25'))
CAP = int(os.environ.get('N20_HARNESS_CAP', '0'))
TOP = int(os.environ.get('N20_HARNESS_TOP', '15'))
RSS_CAP_MB = int(os.environ.get('N20_HARNESS_RSS_CAP', '0'))

tracemalloc.start(25)

TEST_COUNT = 0
GROWTH = []  # (test_id, rss_delta_mb, traced_delta_mb)
START_TRACED = tracemalloc.get_traced_memory()[0] / (1024 * 1024)
# Baseline is taken lazily AFTER the first test completes, so that all
# module imports (Flask app, etc.) are excluded from the diffs.
BASE_SNAP = None
BASE_COUNT = 0


def rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def traced_mb():
    return tracemalloc.get_traced_memory()[0] / (1024 * 1024)


def print_snapshot_diff(label, snap):
    global BASE_SNAP
    if BASE_SNAP is None:
        return
    print(f"\n[harness] === snapshot diff after {label} (vs baseline @ {BASE_COUNT} tests) ===")
    stats = snap.compare_to(BASE_SNAP, 'lineno')
    for st in stats[:TOP]:
        print(f"  {st.size / 1024 / 1024:9.2f} MB  {st.traceback}")
    print(f"[harness]   ... total growth: {sum(s.size for s in stats) / 1024 / 1024:.1f} MB in {len(stats)} sites")


class HarnessPlugin:
    def __init__(self):
        self.prev_rss = rss_mb()
        self.prev_traced = traced_mb()

    def pytest_collection_modifyitems(self, config, items):
        # Truncate the collection up-front so the cap never needs a
        # mid-session abort.
        global CAP
        if CAP and len(items) > CAP:
            print(f"[harness] truncating collection {len(items)} -> {CAP}")
            del items[CAP:]

    def pytest_runtest_logreport(self, report):
        global TEST_COUNT, BASE_SNAP, BASE_COUNT
        if report.when != 'call':
            return
        TEST_COUNT += 1
        gc.collect()
        cur_rss = rss_mb()
        cur_traced = traced_mb()
        GROWTH.append((
            report.nodeid,
            round(cur_rss - self.prev_rss, 1),
            round(cur_traced - self.prev_traced, 2),
        ))
        self.prev_rss = cur_rss
        self.prev_traced = cur_traced

        if TEST_COUNT == 1:
            # All imports are done by now; use this as the baseline.
            BASE_SNAP = tracemalloc.take_snapshot()
            BASE_COUNT = TEST_COUNT

        if RSS_CAP_MB and cur_rss > RSS_CAP_MB:
            print(f"\n[harness] RSS {cur_rss:.0f}MB exceeded cap {RSS_CAP_MB}MB — stopping after {report.nodeid}")
            import pytest
            pytest.exit(f"RSS cap {RSS_CAP_MB}MB exceeded", 99)

        if SAMPLE_EVERY and TEST_COUNT % SAMPLE_EVERY == 0:
            print_snapshot_diff(f"{TEST_COUNT} tests", tracemalloc.take_snapshot())

    def pytest_sessionfinish(self, session, exitstatus):
        # Final snapshot diff, even after an aborted session.
        if TEST_COUNT > BASE_COUNT:
            print_snapshot_diff(f"{TEST_COUNT} tests (final)", tracemalloc.take_snapshot())


def print_report():
    GROWTH.sort(key=lambda g: g[2], reverse=True)
    print("\n[harness] ===== TOP 25 TESTS BY TRACEMEM DELTA =====")
    for tid, rss_d, tr_d in GROWTH[:25]:
        print(f"  traced {tr_d:9.2f} MB | rss {rss_d:7.1f} MB | {tid}")
    n = len(GROWTH)
    if n:
        tot_tr = sum(g[2] for g in GROWTH)
        print(f"[harness] {n} tests; sum of per-test traced deltas {tot_tr:.1f} MB "
              f"(avg {tot_tr / n:.2f} MB/test)")
    print(f"[harness] final RSS {rss_mb():.0f} MB, traced {traced_mb():.1f} MB")


def main():
    import pytest

    extra = sys.argv[1:]
    argv = ['-q', '-p', 'no:cacheprovider', '-p', 'no:cov', '--no-header'] + extra
    print(f"[harness] pytest {argv}")
    print(f"[harness] starting RSS {rss_mb():.0f} MB, traced {traced_mb():.1f} MB")
    rc = 1
    try:
        rc = pytest.main(argv, plugins=[HarnessPlugin()])
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
        print(f"[harness] session aborted: {e}")
    finally:
        print_report()
    return rc if isinstance(rc, int) else 1


if __name__ == '__main__':
    sys.exit(main())
