"""Slice 288 — deadline scheduling.

Covers: earliest-deadline-first ordering, deadline-aware collection
(the window never waits past the earliest deadline), late-task drops
(future fails with SchedulerError, miss counted), drop_late=False
still executes but counts the miss, no-deadline tasks sort last,
config/submit validation, and deadline+priority tiebreak interaction.
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


def _deadline_config(**kw):
    base = {"deadline_enabled": True, "max_batch_size": 8,
            "batch_window_s": 5.0, "max_workers": 2}
    base.update(kw)
    return SchedulerConfig(**base)


# --- validation ---------------------------------------------------------------

def test_deadline_config_validation():
    with pytest.raises(SchedulerError):
        SchedulerConfig(deadline_enabled="yes")
    with pytest.raises(SchedulerError):
        SchedulerConfig(drop_late="yes")


def test_submit_rejects_bad_deadline():
    sched = BatchScheduler(SchedulerConfig(deadline_enabled=True))
    try:
        with pytest.raises(SchedulerError):
            sched.submit(_echo, "x", deadline="soon")
        with pytest.raises(SchedulerError):
            sched.submit(_echo, "x", deadline=True)
        with pytest.raises(SchedulerError, match="already in the past"):
            sched.submit(_echo, "x", deadline=time.monotonic() - 1.0)
    finally:
        sched.shutdown()


# --- EDF ordering ---------------------------------------------------------------

def test_earliest_deadline_first():
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
        _deadline_config(max_batch_size=3, batch_window_s=0.3),
        executor=OrderedExecutor())
    try:
        now = time.monotonic()
        # submit latest-deadline first; EDF must still run earliest first.
        # All three land in one batch (cap 3, back-to-back submits).
        f1 = sched.submit(_echo, "late", deadline=now + 10.0)
        f2 = sched.submit(_echo, "early", deadline=now + 5.0)
        f3 = sched.submit(_echo, "no-deadline")
        for f in (f1, f2, f3):
            f.result(timeout=5)
        assert order == ["early", "late", "no-deadline"], order
    finally:
        sched.shutdown()


def test_deadline_aware_collection_ignores_long_window():
    """A lone task with a tight deadline must not wait out a 5s window."""
    sched = BatchScheduler(_deadline_config())
    try:
        start = time.monotonic()
        future = sched.submit(_echo, "urgent",
                              deadline=time.monotonic() + 0.15)
        assert future.result(timeout=5) == "urgent"
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"waited out the window: {elapsed:.2f}s"
    finally:
        sched.shutdown()


# --- drops and misses ---------------------------------------------------------------

class SlowExecutor(BatchExecutor):
    """Each batch takes 0.3s — lets queued deadlines expire."""

    def execute_batch(self, tasks):
        time.sleep(0.3)
        for task in tasks:
            task.future.set_result(task.args[0])


def test_late_task_dropped_and_counted():
    sched = BatchScheduler(
        _deadline_config(max_batch_size=1, batch_window_s=0.01,
                         drop_late=True),
        executor=SlowExecutor())
    try:
        first = sched.submit(_echo, "first")  # occupies the slow batch
        doomed = sched.submit(_echo, "doomed",
                              deadline=time.monotonic() + 0.1)
        assert first.result(timeout=5) == "first"
        with pytest.raises(SchedulerError, match="missed its deadline"):
            doomed.result(timeout=5)
        assert sched.stats()["deadline_misses"] == 1
    finally:
        sched.shutdown()


def test_drop_late_false_executes_but_counts_miss():
    sched = BatchScheduler(
        _deadline_config(max_batch_size=1, batch_window_s=0.01,
                         drop_late=False),
        executor=SlowExecutor())
    try:
        first = sched.submit(_echo, "first")
        late = sched.submit(_echo, "late",
                            deadline=time.monotonic() + 0.1)
        assert first.result(timeout=5) == "first"
        assert late.result(timeout=5) == "late"  # executed despite lateness
        assert sched.stats()["deadline_misses"] == 1
    finally:
        sched.shutdown()


def test_ontime_tasks_not_counted():
    sched = BatchScheduler(_deadline_config(batch_window_s=0.05))
    try:
        futures = [sched.submit(_echo, f"t-{i}",
                                deadline=time.monotonic() + 10.0)
                   for i in range(5)]
        assert [f.result(timeout=5) for f in futures] == \
            [f"t-{i}" for i in range(5)]
        assert sched.stats()["deadline_misses"] == 0
    finally:
        sched.shutdown()


# --- interaction -----------------------------------------------------------------------

def test_deadline_primary_priority_tiebreak():
    order = []
    lock = threading.Lock()

    class OrderedExecutor(BatchExecutor):
        def execute_batch(self, tasks):
            for task in tasks:
                tag = task.fn(*task.args, **task.kwargs)
                with lock:
                    order.append(tag)
                task.future.set_result(tag)

    config = _deadline_config(max_batch_size=2, batch_window_s=0.3,
                              priority_enabled=True)
    sched = BatchScheduler(config, executor=OrderedExecutor())
    try:
        now = time.monotonic()
        # same deadline: higher priority wins the tie (one batch of 2)
        f1 = sched.submit(_echo, "low-prio", deadline=now + 5.0, priority=0)
        f2 = sched.submit(_echo, "high-prio", deadline=now + 5.0, priority=9)
        f1.result(timeout=5)
        f2.result(timeout=5)
        assert order == ["high-prio", "low-prio"], order
    finally:
        sched.shutdown()


def test_deadline_disabled_ignores_deadlines():
    config = SchedulerConfig(max_batch_size=1, batch_window_s=0.1)
    sched = BatchScheduler(config)
    try:
        # deadlines accepted at submit (validated) but not scheduled by
        f = sched.submit(_echo, "x", deadline=time.monotonic() + 10.0)
        assert f.result(timeout=5) == "x"
        assert sched.stats()["deadline_enabled"] is False
    finally:
        sched.shutdown()
