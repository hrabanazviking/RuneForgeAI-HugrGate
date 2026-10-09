"""Slice 294 — multiprocess mode.

Covers: submit/map round-trips across real spawned processes,
ordering, up-front picklability validation (callable, args, kwargs,
items), worker exceptions mapped to MultiprocError, task timeouts,
worker crashes (BrokenProcessPool -> MultiprocError), stats, config
validation, and post-shutdown rejection.

Worker functions must be module-level (spawn pickles by reference).
"""

from __future__ import annotations

import os
import threading
import time

import pytest

from hugrgate.errors import MultiprocError
from hugrgate.multiproc import ProcessPool

# --- module-level worker functions (picklable under spawn) ----------------------------


def _add(a, b):
    return a + b


def _square(x):
    return x * x


def _boom(x):
    raise ValueError(f"worker saw {x}")


def _nap(seconds):
    time.sleep(seconds)
    return "woke"


def _crash(_):
    os._exit(1)


# --- tests --------------------------------------------------------------------------------


@pytest.fixture
def pool():
    p = ProcessPool(max_workers=2)
    yield p
    p.shutdown()


def test_submit_round_trip(pool):
    fut = pool.submit(_add, 2, 3)
    assert fut.result(timeout=30) == 5


def test_submit_kwargs(pool):
    assert pool.submit(_add, 2, b=3).result(timeout=30) == 5


def test_map_ordered(pool):
    assert pool.map(_square, [3, 1, 2]) == [9, 1, 4]


def test_map_empty(pool):
    assert pool.map(_square, []) == []


def test_unpicklable_callable_rejected(pool):
    with pytest.raises(MultiprocError, match="cannot be pickled"):
        pool.submit(lambda x: x, 1)


def test_unpicklable_arg_rejected(pool):
    with pytest.raises(MultiprocError, match="task args"):
        pool.submit(_add, threading.Lock(), 1)


def test_unpicklable_kwarg_rejected(pool):
    with pytest.raises(MultiprocError, match="task kwargs"):
        pool.submit(_add, 1, b=threading.Lock())


def test_unpicklable_item_rejected(pool):
    with pytest.raises(MultiprocError, match=r"item\[1\]"):
        pool.map(_square, [1, threading.Lock(), 3])


def test_worker_exception_becomes_multiproc_error(pool):
    with pytest.raises(MultiprocError, match="ValueError"):
        pool.submit(_boom, 7).result(timeout=30)


def test_map_worker_exception(pool):
    with pytest.raises(MultiprocError, match="ValueError"):
        pool.map(_boom, [1, 2])


@pytest.mark.slow
def test_task_timeout():
    p = ProcessPool(max_workers=1, task_timeout_s=1.0)
    try:
        with pytest.raises(MultiprocError, match="timed out"):
            p.submit(_nap, 5).result()
    finally:
        p.shutdown()  # waits out the 5s sleeper


def test_worker_crash_recoverable():
    p = ProcessPool(max_workers=1)
    try:
        with pytest.raises(MultiprocError, match=r"[Cc]rash|died"):
            p.submit(_crash, 0).result(timeout=30)
    finally:
        p.shutdown()


def test_stats(pool):
    pool.submit(_add, 1, 2).result(timeout=30)
    try:
        pool.submit(_boom, 0).result(timeout=30)
    except MultiprocError:
        pass
    stats = pool.stats()
    assert stats["submitted"] == 2
    assert stats["completed"] == 1
    assert stats["failed"] == 1
    assert stats["start_method"] == "spawn"


def test_bad_start_method():
    with pytest.raises(MultiprocError, match="start method"):
        ProcessPool(start_method="teleport")


def test_bad_timeout():
    with pytest.raises(MultiprocError, match="task_timeout_s"):
        ProcessPool(task_timeout_s=0)


def test_submit_after_shutdown():
    p = ProcessPool(max_workers=1)
    p.shutdown()
    with pytest.raises(MultiprocError, match="shut down"):
        p.submit(_add, 1, 2)


def test_shutdown_idempotent():
    p = ProcessPool(max_workers=1)
    p.shutdown()
    p.shutdown()


def test_future_exception_accessor(pool):
    fut = pool.submit(_boom, 1)
    exc = fut.exception(timeout=30)
    assert isinstance(exc, MultiprocError)
    assert "ValueError" in str(exc)
