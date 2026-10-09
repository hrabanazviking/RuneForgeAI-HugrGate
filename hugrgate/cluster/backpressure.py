"""Backpressure protocol. Slice 218.

A node sheds load instead of dying under it. :class:`AdmissionController`
is a token bucket in front of every work-bearing inbound message
(``DECIDE_REQUEST``, ``BATCH_REQUEST``, ``STEAL_REQUEST``): when no
token is available the message is refused with a typed ``QueueFull``
(``code="queue_full"``, recoverable) carrying ``retry_after_ms``.

- Control-plane messages (``HEARTBEAT``, ``GOODBYE``, policy,
  auth) are never shed — shedding the signal that would heal the
  overload is how cascades start.
- The HTTP route maps ``queue_full`` envelopes to **429** with a
  ``Retry-After`` header (slice 218's wire contract); the RPC client
  turns 429 back into ``QueueFull`` so callers can back off and retry.
- The taxonomy error is reused from slice 007 (Anti-Checkbox Rule:
  improve, don't duplicate).
"""

from __future__ import annotations

import threading
import time

from hugrgate.errors import SpecError

__all__ = [
    "DEFAULT_ADMISSION_CAPACITY",
    "DEFAULT_ADMISSION_REFILL_PER_SECOND",
    "AdmissionController",
]

#: Burst size: how many work messages may arrive at once.
DEFAULT_ADMISSION_CAPACITY = 128
#: Sustained rate: tokens per second.
DEFAULT_ADMISSION_REFILL_PER_SECOND = 64.0

#: Message kinds that consume admission tokens (the work plane).
WORK_MESSAGE_TYPES = frozenset({
    "decide_request",
    "batch_request",
    "steal_request",
})


class AdmissionController:
    """Token-bucket admission control. Thread-safe."""

    def __init__(self, capacity: int = DEFAULT_ADMISSION_CAPACITY,
                 refill_per_second: float = (
                     DEFAULT_ADMISSION_REFILL_PER_SECOND)) -> None:
        if not isinstance(capacity, int) or capacity < 1:
            raise SpecError("admission capacity must be a positive int")
        if (not isinstance(refill_per_second, (int, float))
                or refill_per_second <= 0):
            raise SpecError("refill_per_second must be > 0")
        self._capacity = capacity
        self._refill = float(refill_per_second)
        self._tokens = float(capacity)
        self._last = time.monotonic()
        self._lock = threading.RLock()
        self._admitted = 0
        self._refused = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    def _refill_locked(self, now: float) -> None:
        elapsed = now - self._last
        if elapsed > 0:
            self._tokens = min(self._capacity,
                               self._tokens + elapsed * self._refill)
            self._last = now

    def try_acquire(self) -> bool:
        """Take one token; False when the node is shedding load."""
        with self._lock:
            now = time.monotonic()
            self._refill_locked(now)
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                self._admitted += 1
                return True
            self._refused += 1
            return False

    def retry_after_ms(self) -> float:
        """How long until one token is available (for 429 headers)."""
        with self._lock:
            now = time.monotonic()
            self._refill_locked(now)
            if self._tokens >= 1.0:
                return 0.0
            return (1.0 - self._tokens) / self._refill * 1000.0

    def stats(self) -> dict[str, float | int]:
        with self._lock:
            now = time.monotonic()
            self._refill_locked(now)
            return {"capacity": self._capacity,
                    "tokens": self._tokens,
                    "admitted": self._admitted,
                    "refused": self._refused}
