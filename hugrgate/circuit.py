"""Circuit breaker — per-backend failure containment. Slice 18.

States:

- **closed**: traffic flows; consecutive failures are counted.
- **open**: calls are rejected fast (``allow()`` -> False) until
  ``reset_timeout_s`` has elapsed.
- **half-open**: after the timeout, a limited number of probe calls
  (``half_open_max_probes``) are let through. A probe success closes the
  circuit; a probe failure re-opens it and restarts the timeout.

:class:`CircuitRegistry` owns one breaker per backend name and creates
them on demand. :class:`~hugrgate.fallback.FallbackChain` accepts a
registry: open circuits are skipped (recorded in the fallback trace)
and every attempt's outcome is reported back to its breaker.

The clock is injectable (``clock`` parameter) so tests can drive time
deterministically. All methods are thread-safe.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

from hugrgate.log import get_logger

logger = get_logger(__name__)
__all__ = [
    "CLOSED",
    "OPEN",
    "HALF_OPEN",
    "CircuitBreaker",
    "CircuitRegistry",
]

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half-open"


class CircuitBreaker:
    """One backend's circuit breaker."""

    def __init__(self, name: str,
                 failure_threshold: int = 5,
                 reset_timeout_s: float = 30.0,
                 half_open_max_probes: int = 1,
                 clock: Callable[[], float] = time.monotonic):
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if half_open_max_probes < 1:
            raise ValueError("half_open_max_probes must be >= 1")
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout_s = reset_timeout_s
        self.half_open_max_probes = half_open_max_probes
        self._clock = clock
        self._state = CLOSED
        self._consecutive_failures = 0
        self._opened_at: Optional[float] = None
        self._half_open_inflight = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            self._maybe_half_open()
            return self._state

    def _maybe_half_open(self) -> None:
        """Transition open -> half-open once the timeout has elapsed."""
        if (self._state == OPEN and self._opened_at is not None
                and self._clock() - self._opened_at >= self.reset_timeout_s):
            self._state = HALF_OPEN
            self._half_open_inflight = 0
            logger.info("circuit breaker %r half-open (probe admitted)",
                        self.name)

    def allow(self) -> bool:
        """True when a call may proceed (consumes a half-open probe slot)."""
        with self._lock:
            self._maybe_half_open()
            if self._state == CLOSED:
                return True
            if self._state == OPEN:
                return False
            # HALF_OPEN: admit up to half_open_max_probes concurrent probes.
            if self._half_open_inflight < self.half_open_max_probes:
                self._half_open_inflight += 1
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            if self._state == HALF_OPEN:
                self._half_open_inflight = max(
                    0, self._half_open_inflight - 1)
                self._close()
            elif self._state == CLOSED:
                self._consecutive_failures = 0

    def record_failure(self) -> None:
        with self._lock:
            if self._state == HALF_OPEN:
                self._half_open_inflight = max(
                    0, self._half_open_inflight - 1)
                self._open()
            elif self._state == CLOSED:
                self._consecutive_failures += 1
                if self._consecutive_failures >= self.failure_threshold:
                    self._open()

    def _open(self) -> None:
        self._state = OPEN
        self._opened_at = self._clock()
        logger.info("circuit breaker %r opened after %d consecutive failures",
                    self.name, self._consecutive_failures)

    def _close(self) -> None:
        if self._state != CLOSED:
            logger.info("circuit breaker %r closed", self.name)
        self._state = CLOSED
        self._consecutive_failures = 0
        self._opened_at = None
        self._half_open_inflight = 0

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            self._maybe_half_open()
            return {"name": self.name, "state": self._state,
                    "consecutive_failures": self._consecutive_failures}


class CircuitRegistry:
    """Owns the per-backend circuit breakers."""

    def __init__(self, failure_threshold: int = 5,
                 reset_timeout_s: float = 30.0,
                 half_open_max_probes: int = 1,
                 clock: Callable[[], float] = time.monotonic):
        self._defaults: Dict[str, Any] = {
            "failure_threshold": failure_threshold,
            "reset_timeout_s": reset_timeout_s,
            "half_open_max_probes": half_open_max_probes,
        }
        self._clock = clock
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get(self, name: str) -> CircuitBreaker:
        """Return the breaker for ``name``, creating it on first use."""
        with self._lock:
            breaker = self._breakers.get(name)
            if breaker is None:
                breaker = CircuitBreaker(name, clock=self._clock,
                                         **self._defaults)
                self._breakers[name] = breaker
            return breaker

    def configure(self, name: str, **kwargs) -> CircuitBreaker:
        """Create (or replace) the breaker for ``name`` with overrides."""
        with self._lock:
            params = {**self._defaults, **kwargs}
            breaker = CircuitBreaker(name, clock=self._clock, **params)
            self._breakers[name] = breaker
            return breaker

    def snapshot(self) -> Dict[str, Dict[str, object]]:
        with self._lock:
            breakers = list(self._breakers.values())
        return {b.name: b.snapshot() for b in breakers}
