"""Offline peer recovery. Slice 220.

A peer that goes dark isn't hammered with retries — it's backed off
exponentially and, when the backoff elapses, given a **rejoin
handshake**: ping, and on success reset every per-peer monitor
(health, latency, cost, liveness) so the peer rejoins with a clean
slate instead of its failure history, then re-push the cluster policy
so it's current.

:class:`RecoveryManager` owns the backoff clock; ``node.recover_peer``
owns the handshake. Recovery never raises: a failed handshake just
lengthens the backoff.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from hugrgate.errors import SpecError

__all__ = [
    "DEFAULT_RECOVERY_BASE_DELAY_S",
    "DEFAULT_RECOVERY_MAX_DELAY_S",
    "RecoveryManager",
]

#: First retry delay after a failure.
DEFAULT_RECOVERY_BASE_DELAY_S = 1.0
#: Backoff never exceeds this.
DEFAULT_RECOVERY_MAX_DELAY_S = 300.0


class RecoveryManager:
    """Exponential backoff for dark peers. Thread-safe."""

    def __init__(self,
                 base_delay_s: float = DEFAULT_RECOVERY_BASE_DELAY_S,
                 max_delay_s: float = DEFAULT_RECOVERY_MAX_DELAY_S,
                 clock: Callable[[], float] | None = None) -> None:
        if base_delay_s <= 0:
            raise SpecError("base_delay_s must be > 0")
        if max_delay_s < base_delay_s:
            raise SpecError("max_delay_s must be >= base_delay_s")
        self._base = base_delay_s
        self._max = max_delay_s
        self._clock = clock or time.monotonic
        self._failures: dict[str, int] = {}
        self._last_attempt: dict[str, float] = {}
        self._lock = threading.RLock()

    def note_failure(self, node_id: str) -> None:
        """Record a failed contact; lengthens the backoff."""
        with self._lock:
            self._failures[node_id] = self._failures.get(node_id, 0) + 1

    def note_success(self, node_id: str) -> None:
        """Record a success; clears failures and backoff."""
        with self._lock:
            self._failures.pop(node_id, None)
            self._last_attempt.pop(node_id, None)

    def consecutive_failures(self, node_id: str) -> int:
        with self._lock:
            return self._failures.get(node_id, 0)

    def _delay(self, failures: int) -> float:
        if failures <= 0:
            return 0.0
        return min(self._max, self._base * (2.0 ** min(failures - 1, 31)))

    def backoff_s(self, node_id: str) -> float:
        """Current backoff delay: ``base * 2**(failures-1)``, capped."""
        with self._lock:
            failures = self._failures.get(node_id, 0)
        return self._delay(failures)

    def mark_attempt(self, node_id: str) -> None:
        """Record that a retry was just attempted."""
        with self._lock:
            self._last_attempt[node_id] = self._clock()

    def retry_after_s(self, node_id: str) -> float:
        """Seconds until the next retry is allowed (0 = now)."""
        with self._lock:
            last = self._last_attempt.get(node_id)
            failures = self._failures.get(node_id, 0)
        if failures == 0:
            return 0.0
        delay = self._delay(failures)
        if last is None:
            return 0.0
        return max(0.0, last + delay - self._clock())

    def should_retry(self, node_id: str) -> bool:
        """True when a retry attempt is due."""
        return self.retry_after_s(node_id) <= 0.0

    def dark_peers(self) -> list[str]:
        """Peers with outstanding failures."""
        with self._lock:
            return [nid for nid, n in self._failures.items() if n > 0]
