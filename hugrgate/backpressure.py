"""Local backpressure engine — admission control for hot paths. Slice 289.

The cluster has :class:`AdmissionController <hugrgate.cluster.backpressure.AdmissionController>`
(slice 218) for *remote* work messages; this module is the *local*
counterpart, guarding in-process producers (the slice-285 scheduler,
the daemon queue) with the same philosophy — shed load instead of
dying under it — but generic over any callable work:

- :class:`TokenBucket` — thread-safe rate limiter (capacity burst,
  sustained refill).
- :class:`BackpressureEngine` — composes a concurrency cap
  (``max_inflight``) with an optional token bucket (``rate_per_second``).
  :meth:`lease` raises :class:`BackpressureError` when saturated
  (carrying ``retry_after_s`` when the rate limiter can compute one);
  the lease releases when the guarded work completes.
- Integration: :class:`BatchScheduler` accepts
  ``backpressure=engine``; :meth:`submit` leases a slot per task and
  releases it when the task's future settles — so saturation surfaces
  as a taxonomy error at the producer, never as an unbounded queue.

Control-plane exemption (the slice-218 lesson): shedding is for *work*.
The engine never sheds leases it didn't issue, and
:meth:`BatchScheduler.drain` / ``shutdown`` bypass admission —
stopping the signal that would heal the overload is how cascades start.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from hugrgate.errors import BackpressureError
from hugrgate.log import get_logger

logger = get_logger(__name__)

__all__ = [
    "BackpressureEngine",
    "Lease",
    "TokenBucket",
]


class TokenBucket:
    """Thread-safe token bucket: burst ``capacity``, refill per second."""

    def __init__(self, capacity: int, refill_per_second: float) -> None:
        if not isinstance(capacity, int) or capacity < 1:
            raise BackpressureError(
                f"bucket capacity must be a positive int, got {capacity!r}")
        if not isinstance(refill_per_second, (int, float)) or \
                refill_per_second <= 0:
            raise BackpressureError(
                f"refill_per_second must be > 0, got {refill_per_second!r}")
        self.capacity = capacity
        self.refill_per_second = float(refill_per_second)
        self._tokens = float(capacity)
        self._last = time.monotonic()
        self._lock = threading.RLock()

    def _refill(self, now: float) -> None:
        elapsed = now - self._last
        if elapsed > 0:
            self._tokens = min(float(self.capacity),
                               self._tokens + elapsed * self.refill_per_second)
            self._last = now

    def take(self, n: int = 1) -> bool:
        """Take ``n`` tokens; False when unavailable (no waiting)."""
        if n < 1:
            raise BackpressureError(
                f"take() needs n >= 1, got {n}")
        with self._lock:
            now = time.monotonic()
            self._refill(now)
            if self._tokens >= n:
                self._tokens -= n
                return True
            return False

    def retry_after_s(self, n: int = 1) -> float:
        """Seconds until ``n`` tokens are available (0 if available now)."""
        with self._lock:
            now = time.monotonic()
            self._refill(now)
            if self._tokens >= n:
                return 0.0
            return (n - self._tokens) / self.refill_per_second

    @property
    def available(self) -> float:
        with self._lock:
            self._refill(time.monotonic())
            return self._tokens


class Lease:
    """One admitted unit of work; release when the work settles."""

    __slots__ = ("_engine", "_released")

    def __init__(self, engine: BackpressureEngine) -> None:
        self._engine = engine
        self._released = False

    def release(self) -> None:
        """Idempotent: releasing twice is a no-op, never an error."""
        if not self._released:
            self._released = True
            self._engine._release(self)

    def __enter__(self) -> Lease:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()

    @property
    def released(self) -> bool:
        return self._released


class BackpressureEngine:
    """Admission control: concurrency cap + optional rate limit.

    Parameters
    ----------
    max_inflight: hard cap on concurrently leased (not yet released)
        work units.
    rate_per_second: optional sustained admission rate; ``burst_capacity``
        bounds the burst (defaults to ``rate_per_second``).
    """

    def __init__(self, max_inflight: int = 128,
                 rate_per_second: float | None = None,
                 burst_capacity: int | None = None) -> None:
        if not isinstance(max_inflight, int) or max_inflight < 1:
            raise BackpressureError(
                f"max_inflight must be a positive int, got {max_inflight!r}")
        self.max_inflight = max_inflight
        self._bucket: TokenBucket | None = None
        if rate_per_second is not None:
            self._bucket = TokenBucket(
                burst_capacity if burst_capacity is not None
                else max(1, int(rate_per_second)),
                rate_per_second)
        self._lock = threading.RLock()
        self._inflight = 0
        self._admitted = 0
        self._rejected_inflight = 0
        self._rejected_rate = 0

    def lease(self) -> Lease:
        """Admit one work unit; raise :class:`BackpressureError` if full.

        The error carries ``reason`` (``"inflight_cap"`` or
        ``"rate_limit"``) and, for rate limiting, ``retry_after_s``.
        """
        with self._lock:
            if self._inflight >= self.max_inflight:
                self._rejected_inflight += 1
                raise BackpressureError(
                    f"backpressure: {self._inflight} units in flight "
                    f"(cap {self.max_inflight}); shed load and retry",
                    reason="inflight_cap", retry_after_s=None)
            if self._bucket is not None and not self._bucket.take():
                self._rejected_rate += 1
                retry = self._bucket.retry_after_s()
                raise BackpressureError(
                    f"backpressure: admission rate exceeded; retry after "
                    f"{retry:.3f}s",
                    reason="rate_limit", retry_after_s=retry)
            self._inflight += 1
            self._admitted += 1
            return Lease(self)

    def try_lease(self) -> Lease | None:
        """Like :meth:`lease`, but returns None instead of raising."""
        try:
            return self.lease()
        except BackpressureError:
            return None

    def _release(self, _lease: Lease) -> None:
        with self._lock:
            if self._inflight > 0:
                self._inflight -= 1
            else:  # pragma: no cover - defensive; release is idempotent
                logger.warning("backpressure lease released with "
                               "inflight == 0")

    def stats(self) -> dict[str, Any]:
        """Admission statistics snapshot."""
        with self._lock:
            return {
                "max_inflight": self.max_inflight,
                "inflight": self._inflight,
                "admitted_total": self._admitted,
                "rejected_total":
                    self._rejected_inflight + self._rejected_rate,
                "rejected_inflight_cap": self._rejected_inflight,
                "rejected_rate_limit": self._rejected_rate,
                "rate_limited": self._bucket is not None,
                "bucket_available":
                    self._bucket.available if self._bucket else None,
            }
