"""Run blocking work off the Socket.IO / eventlet request greenlet."""
from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar, Optional

T = TypeVar("T")

_POOL_SIZE = int(os.environ.get("N20_BLOCKING_POOL_SIZE", "4"))
_executor = ThreadPoolExecutor(max_workers=_POOL_SIZE, thread_name_prefix="n20-blocking")
_eventlet_tpool = None
_eventlet_probe_lock = threading.Lock()


def offload_blocking_enabled() -> bool:
    return os.environ.get("N20_OFFLOAD_BLOCKING", "true").lower() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


def _use_eventlet_tpool() -> bool:
    global _eventlet_tpool
    if _eventlet_tpool is not None:
        return _eventlet_tpool
    with _eventlet_probe_lock:
        if _eventlet_tpool is not None:
            return _eventlet_tpool
        try:
            from eventlet import tpool  # noqa: F401

            _eventlet_tpool = True
        except Exception:
            _eventlet_tpool = False
    return _eventlet_tpool


def run_blocking(func: Callable[..., T], /, *args, **kwargs) -> T:
    """Execute ``func`` in a real OS thread pool (eventlet tpool or ThreadPoolExecutor)."""
    if not offload_blocking_enabled():
        return func(*args, **kwargs)

    if _use_eventlet_tpool():
        from eventlet import tpool

        return tpool.execute(func, *args, **kwargs)

    future = _executor.submit(func, *args, **kwargs)
    return future.result()


def shutdown_blocking_pool(wait: bool = False) -> None:
    _executor.shutdown(wait=wait)
