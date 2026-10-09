"""Slice 487 — concurrency race hunt.

Slice 017 audited thread-safety; this slice keeps it honest with a
reusable hammer (``hugrgate/gauntlet/racehunt.py``): N threads
rendezvous on a barrier (real contention, not polite turns),
exceptions are captured with tracebacks, and a caller-supplied
invariant is the actual race detector. Pinned targets:
``DecisionCache`` (put/get/invalidate) and ``BackendRegistry``
(register/get/list).
"""

from __future__ import annotations

import threading

import pytest

from hugrgate.gauntlet.racehunt import (
    HammerReport,
    RaceHuntError,
    hammer,
    hammer_cache,
    hammer_registry,
)


def test_hammer_rejects_bad_args():
    with pytest.raises(ValueError):
        hammer(lambda t, i: None, threads=0)
    with pytest.raises(ValueError):
        hammer(lambda t, i: None, iterations=0)


def test_hammer_captures_worker_exceptions():
    def _boom(tid: int, i: int) -> None:
        raise RuntimeError("worker blew up")

    report = hammer(_boom, threads=2, iterations=3)
    assert not report.ok
    assert len(report.errors) == 2
    assert "worker blew up" in report.errors[0]
    with pytest.raises(RaceHuntError):
        report.raise_if_failed("boom-test")


def test_hammer_detects_a_real_race():
    """The invariant mechanism is proven against a deliberately racy
    counter. All threads read the same value behind a barrier, then
    all write ``value + 1`` — the lost updates are structural, not
    timing luck, so the hunt must fail deterministically."""
    threads, iterations = 4, 200
    counter = [0]
    sync = threading.Barrier(threads)

    def _racy(tid: int, i: int) -> None:
        value = counter[0]
        sync.wait(timeout=30)
        counter[0] = value + 1

    def _invariant():
        return counter[0] == threads * iterations, f"counter={counter[0]}"

    report = hammer(_racy, threads=threads, iterations=iterations,
                    invariant=_invariant)
    assert not report.ok
    assert report.invariant_ok is False
    assert counter[0] == iterations  # every round collapsed to +1


def test_hammer_passes_with_lock():
    counter = [0]
    lock = threading.Lock()

    def _safe(tid: int, i: int) -> None:
        with lock:
            counter[0] += 1

    report = hammer(_safe, threads=4, iterations=500,
                    invariant=lambda: (counter[0] == 2000,
                                       f"counter={counter[0]}"))
    assert report.ok
    report.raise_if_failed("locked-counter")  # must not raise


def test_cache_survives_hammer():
    report = hammer_cache(threads=8, iterations=200)
    assert report.ok, (report.errors, report.invariant_detail)
    report.raise_if_failed("DecisionCache")


def test_registry_survives_hammer():
    report = hammer_registry(threads=8, iterations=200)
    assert report.ok, (report.errors, report.invariant_detail)
    report.raise_if_failed("BackendRegistry")


def test_report_shape():
    report = HammerReport(threads=2, iterations=3, elapsed_s=0.01)
    assert report.ok
    assert report.errors == ()
