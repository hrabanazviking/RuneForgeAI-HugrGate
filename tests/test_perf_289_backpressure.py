"""Slice 289 — backpressure engine.

Covers: TokenBucket take/refill/retry_after/validation, engine
inflight-cap admission and rejection (reason + details), rate-limit
rejection with retry_after_s, try_lease, lease idempotent release and
context-manager use, stats shape, and BatchScheduler integration
(saturation raises BackpressureError at the producer; slots release
when tasks settle).
"""

from __future__ import annotations

import threading
import time

import pytest

from hugrgate.backpressure import BackpressureEngine, Lease, TokenBucket
from hugrgate.errors import BackpressureError
from hugrgate.scheduler import (
    BatchExecutor,
    BatchScheduler,
    SchedulerConfig,
)

# --- TokenBucket ---------------------------------------------------------------------

def test_bucket_take_and_refill():
    bucket = TokenBucket(capacity=2, refill_per_second=20.0)
    assert bucket.take()
    assert bucket.take()
    assert not bucket.take()
    time.sleep(0.06)  # ~1.2 tokens refill
    assert bucket.take()
    assert not bucket.take()


def test_bucket_retry_after():
    bucket = TokenBucket(capacity=1, refill_per_second=10.0)
    assert bucket.take()
    assert bucket.retry_after_s() == pytest.approx(0.1, abs=0.03)
    assert bucket.retry_after_s() >= 0.0


def test_bucket_available_now_reports_zero():
    bucket = TokenBucket(capacity=3, refill_per_second=10.0)
    assert bucket.retry_after_s() == 0.0


def test_bucket_validation():
    with pytest.raises(BackpressureError):
        TokenBucket(capacity=0, refill_per_second=1.0)
    with pytest.raises(BackpressureError):
        TokenBucket(capacity=2, refill_per_second=0)
    with pytest.raises(BackpressureError):
        TokenBucket(capacity=2, refill_per_second=1.0).take(0)


# --- engine -------------------------------------------------------------------------------

def test_engine_inflight_cap():
    engine = BackpressureEngine(max_inflight=2)
    a = engine.lease()
    b = engine.lease()
    with pytest.raises(BackpressureError) as exc:
        engine.lease()
    assert exc.value.code == "backpressure_error"
    assert exc.value.recoverable is True
    assert exc.value.details["reason"] == "inflight_cap"
    assert exc.value.details["retry_after_s"] is None
    b.release()
    c = engine.lease()  # slot freed
    assert isinstance(c, Lease)
    a.release()
    c.release()
    assert engine.stats()["inflight"] == 0


def test_try_lease_returns_none_when_full():
    engine = BackpressureEngine(max_inflight=1)
    lease = engine.lease()
    assert engine.try_lease() is None
    lease.release()
    assert engine.try_lease() is not None


def test_lease_release_idempotent():
    engine = BackpressureEngine(max_inflight=1)
    lease = engine.lease()
    lease.release()
    lease.release()  # no-op, never an error
    assert lease.released
    assert engine.stats()["inflight"] == 0
    # and the slot really is free
    engine.lease().release()


def test_lease_context_manager():
    engine = BackpressureEngine(max_inflight=1)
    with engine.lease():
        assert engine.stats()["inflight"] == 1
    assert engine.stats()["inflight"] == 0


def test_rate_limit_rejection_carries_retry_after():
    engine = BackpressureEngine(max_inflight=100, rate_per_second=5.0,
                                burst_capacity=1)
    engine.lease()
    with pytest.raises(BackpressureError) as exc:
        engine.lease()
    assert exc.value.details["reason"] == "rate_limit"
    retry = exc.value.details["retry_after_s"]
    assert retry == pytest.approx(0.2, abs=0.05)
    stats = engine.stats()
    assert stats["rejected_rate_limit"] == 1
    assert stats["rate_limited"] is True


def test_engine_validation():
    with pytest.raises(BackpressureError):
        BackpressureEngine(max_inflight=0)


def test_engine_stats_shape():
    engine = BackpressureEngine(max_inflight=4, rate_per_second=10.0)
    lease = engine.lease()
    stats = engine.stats()
    assert stats["max_inflight"] == 4
    assert stats["inflight"] == 1
    assert stats["admitted_total"] == 1
    assert stats["rejected_total"] == 0
    lease.release()


def test_engine_thread_safe_admission():
    engine = BackpressureEngine(max_inflight=8)
    admitted = []
    lock = threading.Lock()

    def _grab():
        try:
            lease = engine.lease()
        except BackpressureError:
            return
        with lock:
            admitted.append(lease)
        time.sleep(0.02)
        lease.release()

    threads = [threading.Thread(target=_grab) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(admitted) == 8
    assert engine.stats()["inflight"] == 0
    assert engine.stats()["rejected_total"] == 12


# --- scheduler integration -----------------------------------------------------------------------

class BlockingExecutor(BatchExecutor):
    def __init__(self):
        self.gate = threading.Event()

    def execute_batch(self, tasks):
        self.gate.wait(timeout=10)
        for task in tasks:
            try:
                task.future.set_result(task.fn(*task.args, **task.kwargs))
            except Exception as e:  # noqa: BLE001
                task.future.set_exception(e)


def test_scheduler_backpressure_rejects_at_producer():
    engine = BackpressureEngine(max_inflight=2)
    blocking = BlockingExecutor()
    sched = BatchScheduler(
        SchedulerConfig(max_batch_size=10, batch_window_s=0.01,
                        max_queue_depth=100),
        executor=blocking, backpressure=engine)
    try:
        f1 = sched.submit(lambda: "a")
        f2 = sched.submit(lambda: "b")
        time.sleep(0.1)  # both picked up; slots held while blocked
        with pytest.raises(BackpressureError, match="in flight"):
            sched.submit(lambda: "c")
        assert engine.stats()["rejected_total"] == 1
        blocking.gate.set()
        assert f1.result(timeout=5) == "a"
        assert f2.result(timeout=5) == "b"
        # slots released when the tasks settled: admission works again
        f3 = sched.submit(lambda: "c")
        assert f3.result(timeout=5) == "c"
        assert engine.stats()["inflight"] == 0
    finally:
        blocking.gate.set()
        sched.shutdown()


def test_scheduler_without_engine_unchanged():
    sched = BatchScheduler(SchedulerConfig(batch_window_s=0.01))
    try:
        assert sched.backpressure is None
        assert sched.submit(lambda: 1).result(timeout=5) == 1
        assert sched.stats()["backpressure"] is None
    finally:
        sched.shutdown()


def test_scheduler_rejects_bad_engine_type():
    with pytest.raises(Exception):
        BatchScheduler(backpressure=object())
