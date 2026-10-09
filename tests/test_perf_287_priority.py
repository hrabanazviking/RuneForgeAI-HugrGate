"""Slice 287 — priority scheduling.

Covers: high-priority queue jumping (batch composition asserted via a
recording executor), FIFO within a priority level, starvation freedom
under continuous high-priority pressure (aging boost), default FIFO
preservation when disabled, and config/submit validation.
"""

from __future__ import annotations

import threading
import time

import pytest

from hugrgate.errors import SchedulerError
from hugrgate.scheduler import (
    BatchExecutor,
    BatchScheduler,
    SchedulerConfig,
)


def _echo(tag):
    return tag


def _priority_config(**kw):
    base = {"priority_enabled": True, "max_batch_size": 4,
            "batch_window_s": 0.2, "max_workers": 2,
            "starvation_horizon_s": 30.0}
    base.update(kw)
    return SchedulerConfig(**base)


# --- validation ---------------------------------------------------------------

def test_priority_config_validation():
    with pytest.raises(SchedulerError):
        SchedulerConfig(priority_enabled="yes")
    with pytest.raises(SchedulerError):
        SchedulerConfig(starvation_horizon_s=0)
    with pytest.raises(SchedulerError):
        SchedulerConfig(starvation_horizon_s=-5)


def test_submit_rejects_non_int_priority():
    sched = BatchScheduler(SchedulerConfig(priority_enabled=True))
    try:
        with pytest.raises(SchedulerError):
            sched.submit(_echo, "x", priority="high")
        with pytest.raises(SchedulerError):
            sched.submit(_echo, "x", priority=1.5)
    finally:
        sched.shutdown()


# --- ordering ---------------------------------------------------------------------

def test_high_priority_jumps_the_queue():
    completed_batches: list[list[str]] = []
    lock = threading.Lock()

    class TaggingExecutor(BatchExecutor):
        def execute_batch(self, tasks):
            tags = [task.args[0] for task in tasks]
            with lock:
                completed_batches.append(tags)
            for task, tag in zip(tasks, tags, strict=True):
                task.future.set_result(tag)

    sched = BatchScheduler(_priority_config(max_batch_size=2,
                                            batch_window_s=0.3),
                           executor=TaggingExecutor())
    try:
        lows = [sched.submit(_echo, f"low-{i}", priority=0)
                for i in range(3)]
        high = sched.submit(_echo, "high", priority=10)
        assert high.result(timeout=5) == "high"
        assert [f.result(timeout=5) for f in lows] == \
            [f"low-{i}" for i in range(3)]
        # the high-priority task made the first batch despite arriving last
        assert "high" in completed_batches[0]
        assert len(completed_batches[0]) == 2
    finally:
        sched.shutdown()


def test_high_priority_executes_first_deterministically():
    """Single-slot batches make execution order fully observable."""
    order = []
    lock = threading.Lock()

    class OrderedExecutor(BatchExecutor):
        def execute_batch(self, tasks):
            for task in tasks:
                tag = task.fn(*task.args, **task.kwargs)
                with lock:
                    order.append(tag)
                task.future.set_result(tag)

    sched = BatchScheduler(
        _priority_config(max_batch_size=1, batch_window_s=0.25),
        executor=OrderedExecutor())
    try:
        futures = [sched.submit(_echo, f"low-{i}", priority=0)
                   for i in range(3)]
        futures.append(sched.submit(_echo, "high", priority=10))
        for f in futures:
            f.result(timeout=5)
        assert order[0] == "high", f"expected high first, got {order}"
        # FIFO among the lows
        assert order[1:] == ["low-0", "low-1", "low-2"]
    finally:
        sched.shutdown()


def test_fifo_preserved_when_priority_disabled():
    order = []
    lock = threading.Lock()

    class OrderedExecutor(BatchExecutor):
        def execute_batch(self, tasks):
            for task in tasks:
                tag = task.fn(*task.args, **task.kwargs)
                with lock:
                    order.append(tag)
                task.future.set_result(tag)

    config = SchedulerConfig(max_batch_size=1, batch_window_s=0.15)
    sched = BatchScheduler(config, executor=OrderedExecutor())
    try:
        futures = [sched.submit(_echo, f"t-{i}", priority=10 - i)
                   for i in range(4)]
        for f in futures:
            f.result(timeout=5)
        # priority disabled: submission order wins, priorities ignored
        assert order == ["t-0", "t-1", "t-2", "t-3"]
    finally:
        sched.shutdown()


# --- starvation freedom ---------------------------------------------------------------

def test_no_starvation_under_continuous_pressure():
    """Aging: a low-priority task must complete despite endless highs."""
    config = _priority_config(max_batch_size=1, batch_window_s=0.01,
                              starvation_horizon_s=0.05)
    sched = BatchScheduler(config)
    stop = threading.Event()
    try:
        low = sched.submit(_echo, "low", priority=0)

        def _pressure():
            while not stop.is_set():
                try:
                    sched.submit(_echo, "high", priority=10)
                except SchedulerError:
                    pass  # queue full is fine; pressure continues
                time.sleep(0.005)

        pump = threading.Thread(target=_pressure, daemon=True)
        pump.start()
        # priority gap is 10, horizon 0.05s: the low task's boost reaches
        # 10 after 0.5s of waiting, then it outranks fresh highs.
        assert low.result(timeout=10) == "low"
        stop.set()
        pump.join(timeout=5)
    finally:
        stop.set()
        sched.shutdown()


def test_stats_reports_priority_flag():
    sched = BatchScheduler(_priority_config())
    try:
        assert sched.stats()["priority_enabled"] is True
    finally:
        sched.shutdown()
    plain = BatchScheduler()
    try:
        assert plain.stats()["priority_enabled"] is False
    finally:
        plain.shutdown()
