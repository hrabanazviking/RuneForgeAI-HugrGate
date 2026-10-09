"""Slice 295 — worker supervision.

Covers: heartbeat-healthy workers are left alone, stale heartbeats
trigger restart, dead threads (exception / silent return) trigger
restart, restart-budget exhaustion escalates (handler called, no
further restarts), remove_worker, config validation, double start,
unknown worker, and stats shape.
"""

from __future__ import annotations

import threading
import time

import pytest

from hugrgate.errors import SupervisionError
from hugrgate.supervision import Supervisor, WorkerContext


def _healthy(ctx: WorkerContext):
    while not ctx.should_stop:
        ctx.heartbeat()
        time.sleep(0.05)


def _staller(ctx: WorkerContext):
    # Beats once, then never again (but stays alive).
    ctx.heartbeat()
    while not ctx.should_stop:
        time.sleep(0.05)


_boom_armed = threading.Event()


def _raiser(ctx: WorkerContext):
    ctx.heartbeat()
    if _boom_armed.is_set():
        _boom_armed.clear()
        raise RuntimeError("worker exploded")
    while not ctx.should_stop:
        ctx.heartbeat()
        time.sleep(0.05)


def _quitter(ctx: WorkerContext):
    ctx.heartbeat()
    return  # silent return: thread dies without error


def _wait_for(pred, timeout=10.0, what="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


@pytest.fixture
def sup():
    s = Supervisor(check_interval_s=0.1)
    s.start()
    yield s
    s.stop()


def test_healthy_worker_not_restarted(sup):
    sup.add_worker("ok", _healthy, heartbeat_timeout_s=0.5)
    time.sleep(0.6)
    stats = sup.stats()["workers"]["ok"]
    assert stats["alive"] is True
    assert stats["restarts"] == 0
    assert stats["escalated"] is False


def test_stale_heartbeat_restarts(sup):
    sup.add_worker("stall", _staller, heartbeat_timeout_s=0.3,
                   max_restarts=5)
    _wait_for(lambda: sup.stats()["workers"]["stall"]["restarts"] >= 1,
              what="restart after stale heartbeat")
    # The restarted worker stalls again; restarts accumulate.
    _wait_for(lambda: sup.stats()["workers"]["stall"]["restarts"] >= 2,
              what="second restart")


def test_exception_restarts_worker(sup):
    _boom_armed.set()
    sup.add_worker("boom", _raiser, heartbeat_timeout_s=5.0,
                   max_restarts=5)
    _wait_for(lambda: sup.stats()["workers"]["boom"]["restarts"] >= 1,
              what="restart after exception")
    # The replacement is healthy (the bomb was one-shot).
    _wait_for(lambda: sup.stats()["workers"]["boom"]["alive"] is True,
              what="replacement worker alive")
    assert sup.stats()["workers"]["boom"]["restarts"] == 1


def test_silent_return_restarts_worker(sup):
    sup.add_worker("quit", _quitter, heartbeat_timeout_s=5.0,
                   max_restarts=5)
    _wait_for(lambda: sup.stats()["workers"]["quit"]["restarts"] >= 1,
              what="restart after silent return")


def test_budget_exhaustion_escalates():
    escalations = []
    s = Supervisor(check_interval_s=0.1,
                   on_escalation=lambda n, r, rec: escalations.append((n, r)))
    s.start()
    try:
        s.add_worker("flaky", _staller, heartbeat_timeout_s=0.2,
                     max_restarts=2, restart_window_s=60.0)
        _wait_for(lambda: sup_escalated(s, "flaky"), what="escalation")
        assert len(escalations) == 1
        name, reason = escalations[0]
        assert name == "flaky"
        assert "stale" in reason
        restarts_at_escalation = s.stats()["workers"]["flaky"]["restarts"]
        time.sleep(0.5)
        # No further restarts after escalation.
        assert s.stats()["workers"]["flaky"]["restarts"] == \
            restarts_at_escalation
    finally:
        s.stop()


def sup_escalated(s, name):
    return s.stats()["workers"][name]["escalated"]


def test_remove_worker(sup):
    sup.add_worker("tmp", _healthy, heartbeat_timeout_s=0.5)
    time.sleep(0.2)
    sup.remove_worker("tmp")
    assert "tmp" not in sup.stats()["workers"]
    with pytest.raises(SupervisionError, match="unknown worker"):
        sup.remove_worker("tmp")


def test_duplicate_name_rejected(sup):
    sup.add_worker("dup", _healthy)
    with pytest.raises(SupervisionError, match="already registered"):
        sup.add_worker("dup", _healthy)


def test_double_start_rejected():
    s = Supervisor()
    s.start()
    try:
        with pytest.raises(SupervisionError, match="already started"):
            s.start()
    finally:
        s.stop()


def test_add_before_start_starts_on_start():
    s = Supervisor(check_interval_s=0.1)
    s.add_worker("early", _healthy, heartbeat_timeout_s=0.5)
    assert s.stats()["workers"]["early"]["alive"] is False
    s.start()
    try:
        _wait_for(lambda: s.stats()["workers"]["early"]["alive"],
                  what="worker alive after start")
    finally:
        s.stop()


def test_bad_config_rejected():
    s = Supervisor()
    with pytest.raises(SupervisionError, match="non-empty"):
        s.add_worker("", _healthy)
    with pytest.raises(SupervisionError, match="callable"):
        s.add_worker("x", "not-callable")
    with pytest.raises(SupervisionError, match="heartbeat_timeout_s"):
        s.add_worker("x", _healthy, heartbeat_timeout_s=0)
    with pytest.raises(SupervisionError, match="max_restarts"):
        s.add_worker("x", _healthy, max_restarts=-1)
    with pytest.raises(SupervisionError, match="check_interval_s"):
        Supervisor(check_interval_s=0)


def test_escalation_handler_exception_survives():
    def bad_handler(name, reason, record):
        raise RuntimeError("handler bug")

    s = Supervisor(check_interval_s=0.1, on_escalation=bad_handler)
    s.start()
    try:
        s.add_worker("flaky", _staller, heartbeat_timeout_s=0.2,
                     max_restarts=1, restart_window_s=60.0)
        _wait_for(lambda: sup_escalated(s, "flaky"),
                  what="escalation despite handler bug")
        # Watchdog still alive: add a healthy worker and see it run.
        s.add_worker("ok2", _healthy, heartbeat_timeout_s=1.0)
        time.sleep(0.4)
        assert s.stats()["workers"]["ok2"]["alive"] is True
    finally:
        s.stop()


def test_heartbeat_visible_in_stats(sup):
    sup.add_worker("ok", _healthy, heartbeat_timeout_s=1.0)
    time.sleep(0.3)
    age = sup.stats()["workers"]["ok"]["heartbeat_age_s"]
    assert age is not None and age < 1.0


def test_stop_is_idempotent_and_stops_workers():
    s = Supervisor(check_interval_s=0.05)
    s.add_worker("ok", _healthy, heartbeat_timeout_s=1.0)
    s.start()
    time.sleep(0.2)
    s.stop()
    s.stop()  # idempotent
    assert s.stats()["running"] is False
    # Worker threads are daemon + stopped; give the join a beat.
    _wait_for(lambda: not any(t.name == "supervised-ok"
                              and t.is_alive()
                              for t in threading.enumerate()),
              timeout=6.0, what="worker thread exit")
