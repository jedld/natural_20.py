import os

import pytest

from natural20.concurrency import offload_blocking_enabled, run_blocking


def test_run_blocking_executes_callable():
    assert run_blocking(lambda x: x + 1, 41) == 42


def test_run_blocking_respects_disable_env(monkeypatch):
    monkeypatch.setenv("N20_OFFLOAD_BLOCKING", "false")
    assert not offload_blocking_enabled()
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    assert run_blocking(fn) == "ok"
    assert calls == [1]
