"""Multiprocess execution mode — process pools for CPU-bound fan-out.

Slice 294. Threads share the GIL; CPU-bound batch work (calibration
sweeps, benchmark matrices, bulk replays) scales better across
processes.  :class:`ProcessPool` wraps
:class:`concurrent.futures.ProcessPoolExecutor` with HugrGate
taxonomy errors and a picklability contract:

- Tasks are plain ``(callable, args, kwargs)``.  The callable and all
  arguments must pickle — :meth:`ProcessPool.submit` validates with
  :mod:`pickle` *before* submission and raises :class:`MultiprocError`
  naming the offending object, instead of letting the worker die
  obscurely.
- Worker crashes surface as :class:`MultiprocError` (the pool replaces
  the worker; the task may be retried) — never a raw
  ``BrokenProcessPool``.
- Timeouts raise :class:`MultiprocError` with ``timeout_s`` context.
- Default start method is ``"spawn"``: the gate hosts threads, locks,
  and reapers that do not survive ``fork`` safely.  ``"fork"`` is
  available where the caller can prove it safe.

Results cross the boundary pickled, so return values must pickle too —
a ``MultiprocError`` is raised when a result cannot be delivered.
"""

from __future__ import annotations

import concurrent.futures
import multiprocessing
import pickle
import threading
from collections.abc import Callable, Iterable
from typing import Any

from hugrgate.errors import MultiprocError
from hugrgate.log import get_logger

logger = get_logger(__name__)

__all__ = [
    "ProcessPool",
]


def _check_picklable(obj: Any, what: str) -> None:
    try:
        pickle.dumps(obj)
    except Exception as e:
        raise MultiprocError(
            f"{what} of type {type(obj).__name__} cannot be pickled "
            f"for multiprocess execution: {e}") from e


def _run_task(payload: tuple[Callable, tuple, dict]) -> Any:
    """Worker-side trampoline. Must stay module-level (picklable)."""
    fn, args, kwargs = payload
    return fn(*args, **kwargs)


class ProcessPool:
    """A process pool with HugrGate error taxonomy (slice 294).

    Parameters
    ----------
    max_workers: process count (defaults to CPU count).
    start_method: ``"spawn"`` (default, safe with threads) or
        ``"fork"``.
    task_timeout_s: default per-task timeout for :meth:`map` and
        :meth:`submit` result retrieval (None = wait forever).
    initializer / initargs: worker-process setup hook.
    """

    def __init__(self, *, max_workers: int | None = None,
                 start_method: str = "spawn",
                 task_timeout_s: float | None = None,
                 initializer: Callable | None = None,
                 initargs: tuple = ()) -> None:
        if start_method not in ("spawn", "fork", "forkserver"):
            raise MultiprocError(
                f"unknown start method {start_method!r}; want "
                f"'spawn', 'fork', or 'forkserver'")
        if task_timeout_s is not None and task_timeout_s <= 0:
            raise MultiprocError(
                f"task_timeout_s must be > 0, got {task_timeout_s!r}")
        if initializer is not None:
            _check_picklable(initializer, "initializer")
            _check_picklable(initargs, "initargs")
        self._max_workers = max_workers
        self._start_method = start_method
        self._task_timeout_s = task_timeout_s
        self._initializer = initializer
        self._initargs = initargs
        self._lock = threading.Lock()
        self._executor: concurrent.futures.ProcessPoolExecutor | None = None
        self._shutdown = False
        self._submitted = 0
        self._completed = 0
        self._failed = 0

    # -- lifecycle ---------------------------------------------------------------

    def _ensure(self) -> concurrent.futures.ProcessPoolExecutor:
        with self._lock:
            if self._shutdown:
                raise MultiprocError("process pool is shut down")
            if self._executor is None:
                ctx = multiprocessing.get_context(self._start_method)
                self._executor = concurrent.futures.ProcessPoolExecutor(
                    max_workers=self._max_workers,
                    mp_context=ctx,
                    initializer=self._initializer,
                    initargs=self._initargs)
                logger.info("process pool started (%s, workers=%s)",
                            self._start_method, self._max_workers)
            return self._executor

    def shutdown(self, *, cancel_pending: bool = True) -> None:
        """Shut down the pool and join workers."""
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
            executor, self._executor = self._executor, None
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=cancel_pending)

    # -- submission ------------------------------------------------------------------

    def submit(self, fn: Callable, *args: Any,
               timeout_s: float | None = None, **kwargs: Any
               ) -> _GuardedFuture:
        """Submit one task. Validates picklability up front.

        Returns a Future whose result/exception retrieval translates
        worker-side failures into :class:`MultiprocError`.
        """
        _check_picklable(fn, "task callable")
        _check_picklable(args, "task args")
        _check_picklable(kwargs, "task kwargs")
        executor = self._ensure()
        with self._lock:
            self._submitted += 1
        future = executor.submit(_run_task, (fn, args, kwargs))
        return _GuardedFuture(future, self, timeout_s if timeout_s
                              is not None else self._task_timeout_s)

    def map(self, fn: Callable, items: Iterable[Any],
            *, timeout_s: float | None = None,
            chunksize: int = 1) -> list[Any]:
        """Run ``fn(item)`` for each item across workers, in order.

        Raises :class:`MultiprocError` on the first failure or timeout;
        remaining results are discarded.
        """
        _check_picklable(fn, "task callable")
        item_list = list(items)
        for i, item in enumerate(item_list):
            _check_picklable(item, f"item[{i}]")
        executor = self._ensure()
        with self._lock:
            self._submitted += len(item_list)
        timeout = timeout_s if timeout_s is not None \
            else self._task_timeout_s
        try:
            results = executor.map(
                _run_task,
                ([fn, (item,), {}] for item in item_list),
                timeout=timeout, chunksize=chunksize)
            return [_translate_result(r, self) for r in results]
        except MultiprocError:
            raise
        except Exception as e:
            raise MultiprocError(_describe_failure(e)) from e

    def stats(self) -> dict[str, Any]:
        """Pool statistics snapshot."""
        with self._lock:
            return {
                "max_workers": self._max_workers,
                "start_method": self._start_method,
                "task_timeout_s": self._task_timeout_s,
                "submitted": self._submitted,
                "completed": self._completed,
                "failed": self._failed,
                "shutdown": self._shutdown,
            }

    # -- internal bookkeeping ----------------------------------------------------------

    def _note_done(self, ok: bool) -> None:
        with self._lock:
            if ok:
                self._completed += 1
            else:
                self._failed += 1


def _describe_failure(exc: BaseException) -> str:
    """Human-readable taxonomy message for an executor/worker failure."""
    if isinstance(exc, MultiprocError):
        return str(exc)
    if isinstance(exc, concurrent.futures.TimeoutError):
        return f"multiprocess task timed out: {exc}"
    broken = concurrent.futures.process.BrokenProcessPool
    if isinstance(exc, broken):
        return (f"worker process died; pool replaced it, retry the task: "
                f"{exc}")
    # Worker-side exception: the traceback already crossed the pickle
    # boundary; keep its type name for diagnosis.
    return f"worker raised {type(exc).__name__}: {exc}"


def _translate_result(value: Any, pool: ProcessPool) -> Any:
    pool._note_done(True)
    return value


class _GuardedFuture:
    """Future wrapper translating worker failures to MultiprocError."""

    def __init__(self, inner: concurrent.futures.Future,
                 pool: ProcessPool, timeout_s: float | None) -> None:
        self._inner = inner
        self._pool = pool
        self._timeout_s = timeout_s

    def result(self, timeout: float | None = None) -> Any:
        wait = self._timeout_s if timeout is None else timeout
        try:
            value = self._inner.result(timeout=wait)
        except BaseException as e:
            self._pool._note_done(False)
            if isinstance(e, MultiprocError):
                raise
            raise MultiprocError(_describe_failure(e)) from e
        self._pool._note_done(True)
        return value

    def cancel(self) -> bool:
        return self._inner.cancel()

    def cancelled(self) -> bool:
        return self._inner.cancelled()

    def done(self) -> bool:
        return self._inner.done()

    def add_done_callback(self, fn: Callable) -> None:
        self._inner.add_done_callback(fn)

    def exception(self, timeout: float | None = None) -> BaseException | None:
        try:
            self.result(timeout=timeout)
        except MultiprocError as e:
            return e
        return None
