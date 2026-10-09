"""Slice 194 — edge watchdog tests."""

from __future__ import annotations

import json

import pytest

from hugrgate.edge.watchdog import EdgeWatchdog, MissPolicy, WatchdogError


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0
    def __call__(self) -> float:
        return self.now
    def advance(self, s: float) -> None:
        self.now += s


# --- success ---------------------------------------------------------------------

def test_heartbeat_keeps_ok():
    clock = Clock()
    wd = EdgeWatchdog(10.0, clock=clock)
    clock.advance(9.0)
    assert wd.check() == "ok"
    wd.heartbeat()
    clock.advance(9.0)
    assert wd.check() == "ok"
    assert wd.misses == 0


def test_miss_logs_by_default():
    clock = Clock()
    seen: list[int] = []
    wd = EdgeWatchdog(5.0, clock=clock, on_miss=seen.append)
    clock.advance(6.0)
    assert wd.check() == "missed"
    assert wd.misses == 1 and seen == [1]
    # still missed until a heartbeat arrives; policy fires per check
    assert wd.check() == "missed"
    assert seen == [1, 2]


def test_restart_policy_rearms_and_counts():
    clock = Clock()
    restarts: list[None] = []
    wd = EdgeWatchdog(5.0, clock=clock, policy=MissPolicy.RESTART,
                      on_restart=lambda: restarts.append(None))
    clock.advance(6.0)
    assert wd.check() == "missed"
    assert wd.restarts == 1 and len(restarts) == 1
    # re-armed: ok until the new deadline passes
    assert wd.check() == "ok"
    clock.advance(6.0)
    assert wd.check() == "missed"
    assert wd.restarts == 2


def test_max_misses_latches_exhausted():
    clock = Clock()
    fired: list[int] = []
    wd = EdgeWatchdog(5.0, clock=clock, on_miss=fired.append, max_misses=2)
    clock.advance(6.0)
    wd.check()   # miss 1
    wd.check()   # miss 2 -> exhausted
    assert wd.exhausted
    wd.check()   # miss 3: recorded, policy NOT fired again
    assert wd.misses == 3 and fired == [1, 2]


def test_start_stop_lifecycle():
    wd = EdgeWatchdog(60.0, check_interval_s=60.0)
    assert not wd.running
    wd.start()
    assert wd.running
    wd.start()  # idempotent
    assert wd.running
    wd.stop()
    assert not wd.running
    wd.stop()  # idempotent


def test_status_serializes():
    clock = Clock()
    wd = EdgeWatchdog(5.0, clock=clock)
    clock.advance(6.0)
    wd.check()
    status = wd.status()
    assert status["misses"] == 1
    assert status["policy"] == "log"
    json.dumps(status)


# --- failure -----------------------------------------------------------------------

def test_bad_construction_rejected():
    with pytest.raises(WatchdogError, match="timeout_s"):
        EdgeWatchdog(0)
    with pytest.raises(WatchdogError, match="check_interval_s"):
        EdgeWatchdog(5.0, check_interval_s=0)
    with pytest.raises(WatchdogError, match="max_misses"):
        EdgeWatchdog(5.0, max_misses=0)


def test_restart_without_callback_still_rearms():
    clock = Clock()
    wd = EdgeWatchdog(5.0, clock=clock, policy=MissPolicy.RESTART)
    clock.advance(6.0)
    assert wd.check() == "missed"
    assert wd.restarts == 0  # no callback registered, nothing invoked
    assert wd.check() == "ok"  # but the deadline was re-armed
