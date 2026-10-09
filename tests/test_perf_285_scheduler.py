"""Slice 285 — batch scheduler v2.

Covers: windowed coalescing (bursts become few batches), max_batch_size
splitting, queue-full backpressure (SchedulerError), per-task exception
routing, shutdown drain semantics, stats shape, and config validation.
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
    ThreadPoolBatchExecutor,
)


def _quick(n):
    return n * 2


def _boom():
    raise RuntimeError("task failed")


# --- config validation ----------------------------------------------------------

@pytest.mark.parametrize("kw", [
    {"max_batch_size": 0},
    {"max_batch_size": -2},
    {"batch_window_s": 0},
    {"batch_window_s": -0.1},
    {"max_queue_depth": 0},
    {"max_workers": 0},
    {"shutdown_timeout_s": 0},
])
def test_config_rejects_bad_values(kw):
    with pytest.raises(SchedulerError):
        SchedulerConfig(**kw)


def test_executor_rejects_bad_workers():
    with pytest.raises(SchedulerError):
        ThreadPoolBatchExecutor(max_workers=0)


# --- batching ----------------------------------------------------------------------

def test_burst_coalesces_into_few_batches():
    config = SchedulerConfig(max_batch_size=32, batch_window_s=0.05,
                             max_workers=4)
    sched = BatchScheduler(config)
    try:
        futures = [sched.submit(_quick, i) for i in range(20)]
        results = [f.result(timeout=5) for f in futures]
        assert results == [i * 2 for i in range(20)]
        stats = sched.stats()
        assert stats["tasks_completed"] == 20
        # 20 tasks in a 50ms window must coalesce aggressively
        assert stats["batches"] <= 4, stats
        assert stats["avg_batch_size"] >= 5.0
    finally:
        sched.shutdown()


def test_max_batch_size_splits():
    config = SchedulerConfig(max_batch_size=5, batch_window_s=0.5,
                             max_workers=4)
    sched = BatchScheduler(config)
    try:
        futures = [sched.submit(_quick, i) for i in range(12)]
        assert [f.result(timeout=5) for f in futures] == [i * 2 for i in range(12)]
        stats = sched.stats()
        assert stats["max_batch_size_seen"] <= 5
        assert stats["batches"] >= 3  # 12 / 5 -> at least 3 batches
    finally:
        sched.shutdown()


def test_task_exception_routed_to_its_future():
    sched = BatchScheduler(SchedulerConfig(batch_window_s=0.01))
    try:
        good = sched.submit(_quick, 21)
        bad = sched.submit(_boom)
        assert good.result(timeout=5) == 42
        with pytest.raises(RuntimeError, match="task failed"):
            bad.result(timeout=5)
    finally:
        sched.shutdown()


def test_broken_executor_fails_tasks_with_scheduler_error():
    class Broken(BatchExecutor):
        def execute_batch(self, tasks):
            raise RuntimeError("executor exploded")

    sched = BatchScheduler(SchedulerConfig(batch_window_s=0.01),
                           executor=Broken())
    try:
        future = sched.submit(_quick, 1)
        with pytest.raises(SchedulerError, match="batch executor failed"):
            future.result(timeout=5)
    finally:
        sched.shutdown()


# --- backpressure ----------------------------------------------------------------------

def test_queue_full_raises_scheduler_error():
    # A blocked executor keeps the worker busy; the queue fills up.
    gate = threading.Event()

    class Blocking(BatchExecutor):
        def execute_batch(self, tasks):
            gate.wait(timeout=10)
            for task in tasks:
                task.future.set_result(None)

    config = SchedulerConfig(max_batch_size=100, batch_window_s=10.0,
                             max_queue_depth=4)
    sched = BatchScheduler(config, executor=Blocking())
    try:
        # first task is pulled by the worker immediately; next 4 fill
        # the queue; the 6th must be refused.
        sched.submit(_quick, 0)
        time.sleep(0.1)  # let the worker grab the first task
        for i in range(1, 5):
            sched.submit(_quick, i)
        with pytest.raises(SchedulerError, match="queue full"):
            sched.submit(_quick, 99)
    finally:
        gate.set()
        sched.shutdown()


def test_submit_after_shutdown_rejected():
    sched = BatchScheduler()
    sched.shutdown()
    with pytest.raises(SchedulerError, match="shut down"):
        sched.submit(_quick, 1)


def test_submit_rejects_non_callable():
    sched = BatchScheduler()
    try:
        with pytest.raises(SchedulerError):
            sched.submit("not-callable")
    finally:
        sched.shutdown()


def test_submit_rejects_past_deadline():
    sched = BatchScheduler()
    try:
        with pytest.raises(SchedulerError, match="already in the past"):
            sched.submit(_quick, 1, deadline=time.monotonic() - 1.0)
    finally:
        sched.shutdown()


# --- lifecycle / stats ----------------------------------------------------------------------

def test_drain_waits_for_queued_work():
    config = SchedulerConfig(max_batch_size=100, batch_window_s=0.2,
                             max_workers=2)
    sched = BatchScheduler(config)
    try:
        futures = [sched.submit(_quick, i) for i in range(10)]
        assert sched.drain(timeout=5) is True
        assert all(f.done() for f in futures)
    finally:
        sched.shutdown()


def test_drain_timeout_returns_false():
    class Slow(BatchExecutor):
        def execute_batch(self, tasks):
            time.sleep(0.3)
            for task in tasks:
                task.future.set_result(None)

    config = SchedulerConfig(max_batch_size=100, batch_window_s=10.0)
    sched = BatchScheduler(config, executor=Slow())
    try:
        sched.submit(_quick, 1)
        assert sched.drain(timeout=0.05) is False
    finally:
        sched.shutdown()


def test_stats_shape():
    sched = BatchScheduler()
    try:
        sched.submit(_quick, 1).result(timeout=5)
        stats = sched.stats()
        assert stats["batches"] >= 1
        assert stats["tasks_completed"] == 1
        assert stats["avg_batch_size"] >= 1.0
        assert stats["queue_wait_p50_ms"] >= 0.0
        assert stats["batch_exec_p50_ms"] >= 0.0
        assert stats["queue_depth"] == 0
        assert stats["accepting"] is True
    finally:
        sched.shutdown()
    assert sched.stats()["accepting"] is False


def test_concurrent_submitters():
    sched = BatchScheduler(SchedulerConfig(max_batch_size=16,
                                           batch_window_s=0.02,
                                           max_queue_depth=500,
                                           max_workers=8))
    try:
        futures = []
        lock = threading.Lock()

        def _submit_many():
            batch = [sched.submit(_quick, i) for i in range(25)]
            with lock:
                futures.extend(batch)

        threads = [threading.Thread(target=_submit_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(futures) == 100
        assert sorted(f.result(timeout=10) for f in futures) == \
            sorted(i * 2 for _ in range(4) for i in range(25))
        assert sched.stats()["tasks_completed"] == 100
    finally:
        sched.shutdown()
