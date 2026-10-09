"""Slice 286 — dynamic batching.

Covers: AIMD controller unit semantics (increase under target, decrease
over target, bounds, half-empty batches carry no increase signal,
validation), and end-to-end adaptation (fast executor grows the batch
size to the cap; slow executor shrinks it), plus stats exposure.
"""

from __future__ import annotations

import time

import pytest

from hugrgate.errors import SchedulerError
from hugrgate.scheduler import (
    AdaptiveBatchController,
    BatchExecutor,
    BatchScheduler,
    SchedulerConfig,
)


def _quick(n):
    return n


# --- controller unit semantics ---------------------------------------------------

def test_controller_increases_under_target():
    ctl = AdaptiveBatchController(min_batch_size=1, max_batch_size=8,
                                  target_latency_s=0.05)
    assert ctl.current_size == 1
    # full batches under target grow additively
    assert ctl.observe(0.01, 1) == 2
    assert ctl.observe(0.01, 2) == 3
    snap = ctl.snapshot()
    assert snap["increases"] == 2
    assert snap["decreases"] == 0


def test_controller_decreases_over_target():
    ctl = AdaptiveBatchController(min_batch_size=1, max_batch_size=8,
                                  target_latency_s=0.05,
                                  decrease_factor=0.5)
    ctl.observe(0.01, 1)  # -> 2
    ctl.observe(0.01, 2)  # -> 3
    ctl.observe(0.01, 3)  # -> 4
    assert ctl.observe(0.5, 4) == 2  # multiplicative decrease
    assert ctl.snapshot()["decreases"] == 1


def test_controller_respects_bounds():
    ctl = AdaptiveBatchController(min_batch_size=2, max_batch_size=3,
                                  target_latency_s=0.05)
    assert ctl.current_size == 2
    for _ in range(10):
        ctl.observe(0.001, ctl.current_size)
    assert ctl.current_size == 3  # capped at max
    for _ in range(10):
        ctl.observe(10.0, ctl.current_size)
    assert ctl.current_size == 2  # floored at min


def test_half_empty_batch_carries_no_increase_signal():
    ctl = AdaptiveBatchController(min_batch_size=1, max_batch_size=8,
                                  target_latency_s=0.05)
    ctl.observe(0.01, 1)  # -> 2
    # a batch of 1 while the target is 2 beat the target — but it says
    # nothing about headroom for size 2, so no increase.
    assert ctl.observe(0.001, 1) == 2
    assert ctl.snapshot()["increases"] == 1


def test_over_target_always_decreases_even_when_small():
    ctl = AdaptiveBatchController(min_batch_size=1, max_batch_size=8,
                                  target_latency_s=0.05)
    ctl.observe(0.01, 1)  # -> 2
    # small batch, still over target: back off regardless of size
    assert ctl.observe(0.5, 1) == 1
    assert ctl.snapshot()["decreases"] == 1


def test_controller_rejects_bad_config():
    with pytest.raises(SchedulerError):
        AdaptiveBatchController(min_batch_size=0)
    with pytest.raises(SchedulerError):
        AdaptiveBatchController(min_batch_size=5, max_batch_size=3)
    with pytest.raises(SchedulerError):
        AdaptiveBatchController(target_latency_s=0)
    with pytest.raises(SchedulerError):
        AdaptiveBatchController(additive_increase=0)
    with pytest.raises(SchedulerError):
        AdaptiveBatchController(decrease_factor=1.0)
    with pytest.raises(SchedulerError):
        AdaptiveBatchController(decrease_factor=0.0)


def test_controller_rejects_negative_latency():
    ctl = AdaptiveBatchController()
    with pytest.raises(SchedulerError):
        ctl.observe(-1.0, 1)


def test_config_adaptive_validation():
    with pytest.raises(SchedulerError):
        SchedulerConfig(adaptive=True, min_batch_size=0)
    with pytest.raises(SchedulerError):
        SchedulerConfig(adaptive=True, min_batch_size=9, max_batch_size=8)
    with pytest.raises(SchedulerError):
        SchedulerConfig(adaptive=True, target_batch_latency_s=0)
    with pytest.raises(SchedulerError):
        SchedulerConfig(adaptive="yes")
    # valid adaptive config constructs
    cfg = SchedulerConfig(adaptive=True, min_batch_size=2,
                          max_batch_size=16, target_batch_latency_s=0.02)
    assert cfg.adaptive is True


# --- end-to-end adaptation ---------------------------------------------------

def test_fast_executor_grows_batch_size():
    config = SchedulerConfig(adaptive=True, min_batch_size=1,
                             max_batch_size=8, batch_window_s=0.02,
                             target_batch_latency_s=1.0, max_workers=4)
    sched = BatchScheduler(config)
    try:
        for _ in range(6):
            futures = [sched.submit(_quick, i) for i in range(8)]
            assert [f.result(timeout=5) for f in futures] == list(range(8))
        stats = sched.stats()
        assert stats["adaptive"] is True
        assert stats["adaptive_controller"]["current_size"] == 8
        assert stats["effective_max_batch"] == 8
    finally:
        sched.shutdown()


def test_slow_executor_shrinks_batch_size():
    class Slow(BatchExecutor):
        def execute_batch(self, tasks):
            # latency grows with batch size: big batches blow the budget
            time.sleep(0.01 * len(tasks))
            for task in tasks:
                task.future.set_result(task.args[0])

    config = SchedulerConfig(adaptive=True, min_batch_size=1,
                             max_batch_size=16, batch_window_s=0.05,
                             target_batch_latency_s=0.015, max_workers=4)
    sched = BatchScheduler(config, executor=Slow())
    try:
        for _ in range(8):
            futures = [sched.submit(_quick, i) for i in range(12)]
            assert [f.result(timeout=10) for f in futures] == list(range(12))
        stats = sched.stats()
        assert stats["adaptive_controller"]["decreases"] >= 1
        assert stats["effective_max_batch"] < 16
    finally:
        sched.shutdown()


def test_non_adaptive_scheduler_unchanged():
    sched = BatchScheduler(SchedulerConfig())
    try:
        stats = sched.stats()
        assert stats["adaptive"] is False
        assert stats["effective_max_batch"] == 32
        assert "adaptive_controller" not in stats
    finally:
        sched.shutdown()
