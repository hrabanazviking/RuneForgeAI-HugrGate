"""Slice 253 — backend hang injection tests."""

from __future__ import annotations

import threading
import time

import pytest

from hugrgate.chaos import CRASH, HANG, FaultSpec, FaultyBackend
from hugrgate.errors import BackendUnavailable, SpecError, TimeoutError
from hugrgate.spec import DecisionSpec
from hugrgate.timeout import TimeoutBackend
from tests.conftest import StubBackend


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def _hanger(rate=1.0, seed=21, **params):
    return FaultyBackend(StubBackend(name="hang")).arm(
        FaultSpec(mode=HANG, rate=rate, seed=seed, params=params))


# --- hang semantics ------------------------------------------------------------------

def test_endless_hang_behind_deadline_raises_timeout():
    backend = TimeoutBackend(_hanger(), explicit_deadline_ms=300)
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        backend.evaluate({}, _spec())
    elapsed = time.monotonic() - start
    # The deadline fired; we were never stuck behind the hung call.
    assert elapsed < 10.0


def test_hang_isolation_abandoned_thread_does_not_block_recovery():
    inner = _hanger()
    guarded = TimeoutBackend(inner, explicit_deadline_ms=200)
    with pytest.raises(TimeoutError):
        guarded.evaluate({}, _spec())
    # Disarm: the backend serves again. The hung daemon worker is
    # abandoned — the documented threads-cannot-be-killed limitation
    # shared with hugrgate.timeout.
    inner.disarm(HANG)
    assert guarded.evaluate({}, _spec()).value == "a"
    assert inner.fault_stats()["hang"] == 1


def test_transient_hang_recovers_and_delegates():
    backend = _hanger(hang_s=0.05)
    start = time.monotonic()
    result = backend.evaluate({}, _spec())
    elapsed = time.monotonic() - start
    assert result.value == "a"
    assert elapsed >= 0.05
    assert elapsed < 5.0


def test_hang_param_validation_at_arm_time():
    backend = FaultyBackend(StubBackend())
    with pytest.raises(SpecError, match="'hang_s'"):
        backend.arm(FaultSpec(mode=HANG, params={"hang_s": -1.0}))
    with pytest.raises(SpecError, match="'hang_s'"):
        backend.arm(FaultSpec(mode=HANG, params={"hang_s": "forever"}))
    backend.arm(FaultSpec(mode=HANG, params={"hang_s": 0}))
    assert backend.armed_modes() == [HANG]


def test_hang_mode_is_now_wired():
    backend = FaultyBackend(StubBackend())
    backend.arm(FaultSpec(mode=HANG, rate=0.0))  # no longer rejected
    assert backend.armed_modes() == [HANG]
    assert backend.evaluate({}, _spec()).value == "a"


def test_hang_stats_and_seed_reproducibility():
    def pattern(seed):
        backend = _hanger(rate=0.5, seed=seed, hang_s=0.001)
        hung = []
        for _ in range(20):
            t0 = time.monotonic()
            backend.evaluate({}, _spec())
            hung.append(time.monotonic() - t0 >= 0.001)
        return hung
    assert pattern(7) == pattern(7)
    assert any(pattern(7)) and not all(pattern(7))


def test_crash_takes_priority_over_hang():
    backend = (FaultyBackend(StubBackend())
               .arm(FaultSpec(mode=CRASH, rate=1.0, seed=1))
               .arm(FaultSpec(mode=HANG, rate=1.0, seed=1,
                              params={"hang_s": 0.01})))
    with pytest.raises(BackendUnavailable):  # crash wins, no hang
        backend.evaluate({}, _spec())
    assert backend.fault_stats()["hang"] == 0


def test_hang_on_raw_backend_blocks_until_disarmed_thread_ends():
    # Raw (unguarded) endless hang blocks the calling thread: prove it
    # with a daemon thread and a timeout join, then leave it abandoned.
    backend = _hanger()
    done = threading.Event()
    def call():
        try:
            backend.evaluate({}, _spec())
        except Exception:  # noqa: BLE001 - never happens; documented
            pass
        finally:
            done.set()
    t = threading.Thread(target=call, daemon=True)
    t.start()
    assert done.wait(timeout=2.0) is False  # still hung after 2s
    assert backend.fault_stats()["hang"] == 1
