"""Pytest plugin: per-test wall time and RSS growth, streamed to JSONL.

Usage (bounded, safe):
    systemd-run --user --scope -p MemoryMax=8G -p MemorySwapMax=0 \
        env PYTHONPATH=scripts N20_MEMPROFILE_OUT=/tmp/memprof \
        pytest -p pytest_memprofile -n 4 tests n20-webapp/tests

Each worker writes ``$N20_MEMPROFILE_OUT/<worker>.jsonl``. A ``start`` record is
flushed before every test, so if the cgroup OOM-kills a worker the last line
identifies the culprit. Summarize with ``python scripts/memprofile_report.py``.
"""

import json
import os
import resource
import time

import psutil
import pytest

_proc = psutil.Process()
_fh = None


def _rss_mb():
    return _proc.memory_info().rss / 1048576


def _maxrss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _write(rec):
    if _fh is None:
        return
    _fh.write(json.dumps(rec) + "\n")
    _fh.flush()


def pytest_configure(config):
    global _fh
    out = os.environ.get("N20_MEMPROFILE_OUT")
    if not out:
        return
    os.makedirs(out, exist_ok=True)
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    _fh = open(os.path.join(out, f"{worker}.jsonl"), "a", buffering=1)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    rss0, peak0, t0 = _rss_mb(), _maxrss_mb(), time.perf_counter()
    _write({"ev": "start", "id": item.nodeid, "w": worker, "rss": round(rss0, 1)})
    yield
    rss1, peak1 = _rss_mb(), _maxrss_mb()
    _write({
        "ev": "end",
        "id": item.nodeid,
        "w": worker,
        "dur": round(time.perf_counter() - t0, 3),
        "rss_before": round(rss0, 1),
        "rss_after": round(rss1, 1),
        "rss_delta": round(rss1 - rss0, 1),
        "peak_raise": round(max(0.0, peak1 - peak0), 1),
        "peak": round(peak1, 1),
    })
