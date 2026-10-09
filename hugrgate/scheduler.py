"""Batch scheduler v2 — general-purpose windowed batch engine. Slice 285.

The daemon's :class:`BatchingQueue` (slice 018) is asyncio-only and
coupled to daemon wire types.  This module is the reusable scheduling
core for Campaign XII:

- :class:`BatchScheduler` — thread-safe, works from any thread, no
  event loop required.  Submissions are futures; a background worker
  thread coalesces them into batches (``max_batch_size`` items or
  ``batch_window_s`` expiry, whichever comes first) and hands each
  batch to a :class:`BatchExecutor`.
- :class:`BatchExecutor` — protocol: ``execute_batch(tasks)`` runs one
  batch and settles each task's future.  :class:`ThreadPoolBatchExecutor`
  is the default (each task's callable in a worker thread).
- :class:`SchedulerConfig` — validated knobs (bad values raise
  :class:`SchedulerError`, not ``ValueError``).
- Backpressure: ``max_queue_depth`` submissions beyond capacity raise
  :class:`SchedulerError` (recoverable — shed load, retry later).
- Observability: :meth:`BatchScheduler.stats` reports batches, tasks,
  average batch size, queue-wait p50, and batch-execution p50.

Slices 286-288 extend this engine (adaptive sizing, priority lanes,
deadline scheduling); the task record already carries ``priority`` and
``deadline`` fields so those slices slot in without reshaping.
"""

from __future__ import annotations

import itertools
import statistics
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Protocol

from hugrgate.errors import SchedulerError
from hugrgate.log import get_logger

logger = get_logger(__name__)

__all__ = [
    "AdaptiveBatchController",
    "BatchExecutor",
    "BatchScheduler",
    "SchedulerConfig",
    "ThreadPoolBatchExecutor",
]

_task_ids = itertools.count(1)


class AdaptiveBatchController:
    """AIMD controller for the scheduler's batch size (slice 286).

    After every batch, the observed batch-execution latency is compared
    against ``target_latency_s``:

    - under target: ``size += additive_increase`` (probe for more
      throughput), capped at ``max_batch_size``;
    - over target: ``size = max(min_batch_size, size * decrease_factor)``
      (back off fast).

    This is the classic TCP-style AIMD loop: it converges to the
    largest batch the executor can sustain within the latency budget,
    and re-converges when conditions change.  All state transitions are
    explicit and inspectable via :meth:`snapshot`.
    """

    def __init__(self, min_batch_size: int = 1, max_batch_size: int = 32,
                 target_latency_s: float = 0.05,
                 additive_increase: int = 1,
                 decrease_factor: float = 0.5) -> None:
        if not isinstance(min_batch_size, int) or min_batch_size < 1:
            raise SchedulerError(
                f"min_batch_size must be a positive int, got "
                f"{min_batch_size!r}")
        if not isinstance(max_batch_size, int) or \
                max_batch_size < min_batch_size:
            raise SchedulerError(
                f"max_batch_size must be an int >= min_batch_size, got "
                f"{max_batch_size!r}")
        if not isinstance(target_latency_s, (int, float)) or \
                target_latency_s <= 0:
            raise SchedulerError(
                f"target_latency_s must be > 0, got {target_latency_s!r}")
        if not isinstance(additive_increase, int) or additive_increase < 1:
            raise SchedulerError(
                f"additive_increase must be a positive int, got "
                f"{additive_increase!r}")
        if not isinstance(decrease_factor, (int, float)) or not \
                0.0 < decrease_factor < 1.0:
            raise SchedulerError(
                f"decrease_factor must be in (0, 1), got "
                f"{decrease_factor!r}")
        self.min_batch_size = min_batch_size
        self.max_batch_size = max_batch_size
        self.target_latency_s = float(target_latency_s)
        self.additive_increase = additive_increase
        self.decrease_factor = float(decrease_factor)
        self._lock = threading.Lock()
        self._current = min_batch_size
        self._increases = 0
        self._decreases = 0

    @property
    def current_size(self) -> int:
        """The batch size the scheduler should use right now."""
        with self._lock:
            return self._current

    def observe(self, batch_latency_s: float, batch_size: int) -> int:
        """Feed one batch observation; returns the new target size.

        ``batch_latency_s`` is the measured execution latency of a batch
        of ``batch_size`` tasks.  Only batches that actually filled the
        current target carry signal about headroom — a half-empty batch
        that beat the target tells us nothing about a bigger batch, so
        it never triggers an increase (but an over-target batch always
        triggers a decrease, whatever its size).
        """
        if batch_latency_s < 0:
            raise SchedulerError(
                f"batch_latency_s must be >= 0, got {batch_latency_s!r}")
        with self._lock:
            if batch_latency_s > self.target_latency_s:
                new = max(self.min_batch_size,
                          int(self._current * self.decrease_factor))
                if new < self._current:
                    self._decreases += 1
                self._current = new
            elif batch_size >= self._current:
                new = min(self.max_batch_size,
                          self._current + self.additive_increase)
                if new > self._current:
                    self._increases += 1
                self._current = new
            return self._current

    def snapshot(self) -> dict[str, Any]:
        """Inspectable controller state."""
        with self._lock:
            return {
                "current_size": self._current,
                "min_batch_size": self.min_batch_size,
                "max_batch_size": self.max_batch_size,
                "target_latency_s": self.target_latency_s,
                "increases": self._increases,
                "decreases": self._decreases,
            }


@dataclass
class SchedulerConfig:
    """Validated scheduler knobs."""
    max_batch_size: int = 32
    batch_window_s: float = 0.005
    max_queue_depth: int = 1024
    max_workers: int = 8
    shutdown_timeout_s: float = 10.0
    # Slice 286 — dynamic batching: when True, an AIMD controller varies
    # the effective batch size between min_batch_size and max_batch_size
    # to hold batch-execution latency near target_batch_latency_s.
    adaptive: bool = False
    min_batch_size: int = 1
    target_batch_latency_s: float = 0.05

    def __post_init__(self) -> None:
        if not isinstance(self.max_batch_size, int) or \
                self.max_batch_size < 1:
            raise SchedulerError(
                f"max_batch_size must be a positive int, got "
                f"{self.max_batch_size!r}")
        if not isinstance(self.batch_window_s, (int, float)) or \
                self.batch_window_s <= 0:
            raise SchedulerError(
                f"batch_window_s must be > 0, got {self.batch_window_s!r}")
        if not isinstance(self.max_queue_depth, int) or \
                self.max_queue_depth < 1:
            raise SchedulerError(
                f"max_queue_depth must be a positive int, got "
                f"{self.max_queue_depth!r}")
        if not isinstance(self.max_workers, int) or self.max_workers < 1:
            raise SchedulerError(
                f"max_workers must be a positive int, got "
                f"{self.max_workers!r}")
        if not isinstance(self.shutdown_timeout_s, (int, float)) or \
                self.shutdown_timeout_s <= 0:
            raise SchedulerError(
                f"shutdown_timeout_s must be > 0, got "
                f"{self.shutdown_timeout_s!r}")
        if not isinstance(self.adaptive, bool):
            raise SchedulerError(
                f"adaptive must be a bool, got {self.adaptive!r}")
        if not isinstance(self.min_batch_size, int) or \
                self.min_batch_size < 1:
            raise SchedulerError(
                f"min_batch_size must be a positive int, got "
                f"{self.min_batch_size!r}")
        if self.min_batch_size > self.max_batch_size:
            raise SchedulerError(
                f"min_batch_size ({self.min_batch_size}) must be <= "
                f"max_batch_size ({self.max_batch_size})")
        if not isinstance(self.target_batch_latency_s, (int, float)) or \
                self.target_batch_latency_s <= 0:
            raise SchedulerError(
                f"target_batch_latency_s must be > 0, got "
                f"{self.target_batch_latency_s!r}")


@dataclass
class _Task:
    """One scheduled unit of work."""
    task_id: int
    fn: Callable[..., Any]
    args: tuple
    kwargs: dict
    future: Future
    submitted_at: float
    # Extension points for slices 287 (priority) and 288 (deadlines).
    priority: int = 0
    deadline: float | None = None


class BatchExecutor(Protocol):
    """Executes one batch; settles each task's future."""

    def execute_batch(self, tasks: Sequence[_Task]) -> None:
        """Run ``tasks`` and set each ``task.future`` result/exception."""
        ...


class ThreadPoolBatchExecutor:
    """Default executor: each task's callable runs in a worker thread."""

    def __init__(self, max_workers: int = 8) -> None:
        if not isinstance(max_workers, int) or max_workers < 1:
            raise SchedulerError(
                f"max_workers must be a positive int, got {max_workers!r}")
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="batch-worker")

    def execute_batch(self, tasks: Sequence[_Task]) -> None:
        futures = [self._pool.submit(task.fn, *task.args, **task.kwargs)
                   for task in tasks]
        for pool_future, task in zip(futures, tasks, strict=True):
            try:
                task.future.set_result(pool_future.result())
            except BaseException as e:  # noqa: BLE001 - route to the task
                if not task.future.done():
                    task.future.set_exception(e)

    def shutdown(self, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait)


class BatchScheduler:
    """Windowed batch scheduler (slice 285).

    Parameters
    ----------
    config: validated :class:`SchedulerConfig`.
    executor: the :class:`BatchExecutor` that runs each batch.  Defaults
        to a :class:`ThreadPoolBatchExecutor` sized by the config.
    """

    def __init__(self, config: SchedulerConfig | None = None,
                 executor: BatchExecutor | None = None) -> None:
        self.config = config or SchedulerConfig()
        self.executor = executor or ThreadPoolBatchExecutor(
            max_workers=self.config.max_workers)
        self._queue: deque[_Task] = deque()
        self._cond = threading.Condition()
        self._accepting = True
        self._flush_requested = False
        self._worker = threading.Thread(
            target=self._worker_loop, name="batch-scheduler",
            daemon=True)
        self._in_flight = 0  # batches pulled from the queue, not yet done
        self._batches = 0
        self._tasks_completed = 0
        self._batch_sizes: deque[int] = deque(maxlen=1000)
        self._queue_waits_ms: deque[float] = deque(maxlen=1000)
        self._batch_exec_ms: deque[float] = deque(maxlen=1000)
        self._stats_lock = threading.Lock()
        self._adaptive = None
        if self.config.adaptive:
            self._adaptive = AdaptiveBatchController(
                min_batch_size=self.config.min_batch_size,
                max_batch_size=self.config.max_batch_size,
                target_latency_s=self.config.target_batch_latency_s)
        self._worker.start()

    def _effective_max_batch(self) -> int:
        """Batch-size cap: adaptive target when enabled, else the config."""
        if self._adaptive is not None:
            return self._adaptive.current_size
        return self.config.max_batch_size

    # -- submission -------------------------------------------------------

    def submit(self, fn: Callable[..., Any], *args: Any,
               priority: int = 0,
               deadline: float | None = None,
               **kwargs: Any) -> Future:
        """Schedule ``fn(*args, **kwargs)``; returns a future for its result.

        Raises :class:`SchedulerError` when the scheduler is shut down
        or the queue is at capacity (backpressure — retry later).
        """
        if not callable(fn):
            raise SchedulerError(
                f"submit() needs a callable, got {type(fn).__name__}")
        if deadline is not None and deadline <= time.monotonic():
            raise SchedulerError(
                "deadline is already in the past; refusing to schedule "
                "work that cannot meet its deadline")
        with self._cond:
            if not self._accepting:
                raise SchedulerError("scheduler is shut down")
            if len(self._queue) >= self.config.max_queue_depth:
                raise SchedulerError(
                    f"queue full ({self.config.max_queue_depth}); "
                    f"shed load and retry")
            task = _Task(task_id=next(_task_ids), fn=fn, args=args,
                         kwargs=kwargs, future=Future(),
                         submitted_at=time.monotonic(),
                         priority=priority, deadline=deadline)
            self._queue.append(task)
            self._cond.notify()
            return task.future

    def queue_depth(self) -> int:
        """Current number of tasks waiting for a batch."""
        with self._cond:
            return len(self._queue)

    # -- worker --------------------------------------------------------------

    def _worker_loop(self) -> None:
        while True:
            batch = self._collect_batch()
            if batch is None:  # shutdown with an empty queue
                return
            try:
                self._run_batch(batch)
            finally:
                with self._cond:
                    self._in_flight -= 1
                    self._cond.notify_all()

    def _collect_batch(self) -> list[_Task] | None:
        """Gather up to max_batch_size tasks or until the window expires."""
        with self._cond:
            while self._accepting and not self._queue:
                self._cond.wait()
            if not self._queue:
                return None  # shut down while idle
            batch = [self._queue.popleft()]
            window_end = time.monotonic() + self.config.batch_window_s
            cap = self._effective_max_batch()
            while len(batch) < cap:
                remaining = window_end - time.monotonic()
                if (remaining <= 0 or not self._accepting
                        or self._flush_requested):
                    break
                self._cond.wait(timeout=remaining)
                while self._queue and len(batch) < cap:
                    batch.append(self._queue.popleft())
            # The queue -> in-flight transition is atomic under the lock:
            # drain() can never observe "empty and idle" mid-handoff.
            self._in_flight += 1
            return batch

    def _run_batch(self, batch: list[_Task]) -> None:
        now = time.monotonic()
        for task in batch:
            with self._stats_lock:
                self._queue_waits_ms.append(
                    (now - task.submitted_at) * 1000.0)
        exec_start = time.perf_counter()
        try:
            self.executor.execute_batch(batch)
        except Exception as e:  # noqa: BLE001 - executor bug, not task bug
            logger.error("batch executor failed: %s", e)
            for task in batch:
                if not task.future.done():
                    task.future.set_exception(
                        SchedulerError(f"batch executor failed: {e}"))
        finally:
            exec_ms = (time.perf_counter() - exec_start) * 1000.0
            if self._adaptive is not None:
                self._adaptive.observe(exec_ms / 1000.0, len(batch))
            with self._stats_lock:
                self._batches += 1
                self._tasks_completed += len(batch)
                self._batch_sizes.append(len(batch))
                self._batch_exec_ms.append(exec_ms)

    # -- lifecycle ---------------------------------------------------------------

    def drain(self, timeout: float | None = None) -> bool:
        """Wait until the queue is empty and in-flight batches are done.

        Interrupts the batching window so queued work executes promptly
        instead of waiting out a long window.  Returns True when
        drained, False on timeout.
        """
        deadline = (time.monotonic() + timeout) if timeout else None
        with self._cond:
            self._flush_requested = True
            self._cond.notify_all()
        try:
            with self._cond:
                while self._queue or self._in_flight:
                    if deadline is not None:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            return False
                        self._cond.wait(timeout=remaining)
                    else:
                        self._cond.wait()
                return True
        finally:
            with self._cond:
                self._flush_requested = False

    def shutdown(self, wait: bool = True) -> None:
        """Stop accepting; drain queued work, then halt the worker."""
        with self._cond:
            self._accepting = False
            self._cond.notify_all()
        if wait:
            self.drain(timeout=self.config.shutdown_timeout_s)
            self._worker.join(timeout=self.config.shutdown_timeout_s)
        if isinstance(self.executor, ThreadPoolBatchExecutor):
            self.executor.shutdown(wait=wait)

    # -- observability ---------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Scheduler statistics snapshot."""
        with self._stats_lock:
            sizes = list(self._batch_sizes)
            waits = list(self._queue_waits_ms)
            execs = list(self._batch_exec_ms)
            stats = {
                "batches": self._batches,
                "tasks_completed": self._tasks_completed,
                "avg_batch_size": (sum(sizes) / len(sizes)) if sizes else 0.0,
                "max_batch_size_seen": max(sizes) if sizes else 0,
                "queue_wait_p50_ms": statistics.median(waits) if waits else 0.0,
                "batch_exec_p50_ms": statistics.median(execs) if execs else 0.0,
                "queue_depth": self.queue_depth(),
                "accepting": self._accepting,
                "adaptive": self._adaptive is not None,
                "effective_max_batch": self._effective_max_batch(),
            }
            if self._adaptive is not None:
                stats["adaptive_controller"] = self._adaptive.snapshot()
            return stats
