"""Bulkheads: per-backend concurrency caps (slice 269).

A hanging backend (slice 253) must not be able to starve every other
backend: without isolation, N concurrent ``decide()`` calls against
one stuck backend exhaust the caller's threads and everything else
queues behind them. A :class:`BulkheadExecutor` gives each backend its
own semaphore — a slow backend can only ever occupy its own lanes.

Fail-fast is the default: ``execute(..., timeout_s=0.0)`` raises
:class:`BulkheadRejected` immediately when the backend's lanes are
full instead of queueing unboundedly. The rejection is a signal to
shed load (fail over, degrade, answer from cache) — it is
deliberately *not* retried by the default retry policy (slice 268):
spinning against a full bulkhead with no backoff helps nobody.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, TypeVar

from hugrgate.errors import BulkheadRejected, SpecError

__all__ = ["BulkheadExecutor"]

T = TypeVar("T")


class _BackendLanes:
    """The semaphore and counters for one backend."""

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.semaphore = threading.Semaphore(cap)
        self.in_flight = 0
        self.executed_total = 0
        self.rejected_total = 0


class BulkheadExecutor:
    """Per-backend concurrency bulkhead.

    ``default_cap`` applies to backends without an explicit entry in
    ``caps``. Thread-safe; lanes are created lazily per backend name.
    """

    def __init__(self, default_cap: int = 8,
                 caps: dict[str, int] | None = None) -> None:
        self._default_cap = self._check_cap(default_cap, "default_cap")
        self._configured = {name: self._check_cap(cap, f"caps[{name!r}]")
                            for name, cap in (caps or {}).items()}
        self._lock = threading.RLock()
        self._lanes: dict[str, _BackendLanes] = {}

    @staticmethod
    def _check_cap(cap: int, what: str) -> int:
        if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
            raise SpecError(
                f"{what} must be a positive int, got {cap!r}")
        return cap

    def cap_for(self, backend_name: str) -> int:
        """The concurrency cap applying to ``backend_name``."""
        if not backend_name:
            raise SpecError("backend_name must be non-empty")
        return self._configured.get(backend_name, self._default_cap)

    def _lanes_for(self, backend_name: str) -> _BackendLanes:
        with self._lock:
            lanes = self._lanes.get(backend_name)
            if lanes is None:
                lanes = _BackendLanes(self.cap_for(backend_name))
                self._lanes[backend_name] = lanes
            return lanes

    def execute(self, backend_name: str, fn: Callable[..., T],
                *args: Any, timeout_s: float | None = 0.0,
                **kwargs: Any) -> T:
        """Run ``fn`` in ``backend_name``'s lanes.

        ``timeout_s=0.0`` (default) fails fast with
        :class:`BulkheadRejected` when every lane is busy;
        ``timeout_s=None`` waits indefinitely; a positive value
        waits up to that long. ``fn``'s exceptions propagate
        unchanged — the lane is always released.
        """
        lanes = self._lanes_for(backend_name)
        if timeout_s is None:
            acquired = lanes.semaphore.acquire()
        elif timeout_s <= 0:
            acquired = lanes.semaphore.acquire(blocking=False)
        else:
            acquired = lanes.semaphore.acquire(timeout=timeout_s)
        if not acquired:
            with self._lock:
                lanes.rejected_total += 1
            raise BulkheadRejected(
                f"bulkhead for backend {backend_name!r} is full "
                f"({lanes.cap} in flight)",
                backend_name=backend_name, cap=lanes.cap,
                timeout_s=timeout_s)
        with self._lock:
            lanes.in_flight += 1
        try:
            out = fn(*args, **kwargs)
        finally:
            with self._lock:
                lanes.in_flight -= 1
                lanes.executed_total += 1
            lanes.semaphore.release()
        return out

    def stats(self) -> dict[str, dict[str, Any]]:
        """Per-backend ``{cap, in_flight, executed_total,
        rejected_total}`` snapshot."""
        with self._lock:
            return {name: {"cap": lanes.cap,
                           "in_flight": lanes.in_flight,
                           "executed_total": lanes.executed_total,
                           "rejected_total": lanes.rejected_total}
                    for name, lanes in self._lanes.items()}

    def __repr__(self) -> str:
        return (f"BulkheadExecutor(default_cap={self._default_cap}, "
                f"backends={sorted(self._lanes)})")
