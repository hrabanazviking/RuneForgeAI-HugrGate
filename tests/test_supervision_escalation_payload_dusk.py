"""Slice 13 (dusk, Sif's Loom Wave C): supervision-escalation-payload.

The escalation event fired when a worker exhausts its restart budget
must carry the supervisor's restart history and the last failure --
``restart_times`` and ``last_error`` -- not just the worker name.
"""

import time

from hugrgate.supervision import Supervisor


def _wait_for(cond, timeout_s=10.0, what="condition"):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if cond():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")


def _always_fails(ctx):
    raise RuntimeError("kaboom-worker-failure")


def _silent_quitter(ctx):
    return  # thread dies without an exception


def test_escalation_payload_carries_restart_times_and_last_error():
    events = []
    s = Supervisor(check_interval_s=0.02,
                   on_escalation=lambda n, r, p: events.append((n, r, p)))
    s.start()
    try:
        s.add_worker("flaky", _always_fails, heartbeat_timeout_s=60.0,
                     max_restarts=2, restart_window_s=60.0)
        _wait_for(lambda: events, what="escalation event")
        assert len(events) == 1
        name, _reason, payload = events[0]
        assert name == "flaky"
        assert "thread died" in _reason
        # The payload carries the restart history, not just the name.
        assert "restart_times" in payload
        assert "last_error" in payload
        restart_times = payload["restart_times"]
        assert isinstance(restart_times, list)
        # Budget exhausted after exactly max_restarts restarts.
        assert len(restart_times) == 2
        assert all(t > 0 for t in restart_times)
        assert restart_times == sorted(restart_times)
        # The last failure's traceback survived the escalation.
        last_error = payload["last_error"]
        assert isinstance(last_error, str)
        assert "kaboom-worker-failure" in last_error
        # Restart policy itself is unchanged: no restarts past escalation.
        assert s.stats()["workers"]["flaky"]["restarts"] == 2
        assert s.stats()["workers"]["flaky"]["escalated"] is True
    finally:
        s.stop()


def test_escalation_payload_silent_death_last_error_none():
    events = []
    s = Supervisor(check_interval_s=0.02,
                   on_escalation=lambda n, r, p: events.append((n, r, p)))
    s.start()
    try:
        s.add_worker("quiet", _silent_quitter, heartbeat_timeout_s=60.0,
                     max_restarts=1, restart_window_s=60.0)
        _wait_for(lambda: events, what="escalation event")
        name, _reason2, payload = events[0]
        assert name == "quiet"
        assert len(payload["restart_times"]) == 1
        # No exception ever raised: last_error is honestly None.
        assert payload["last_error"] is None
    finally:
        s.stop()
