"""Backend health scoring — latency, errors, quarantine. Slice 17.

:class:`HealthMonitor` tracks per-backend observations over a bounded
window and derives a ``score()`` in [0, 1]:

    score = (1 - error_rate) * latency_factor

where ``latency_factor = min(1, latency_target_ms / p50_latency_ms)`` —
a backend at or under its latency target keeps a factor of 1.

Backends are **quarantined** when their score drops below
``quarantine_threshold`` (or consecutive failures reach
``max_consecutive_failures``). Quarantine is computed live from the
stats, so a success **auto-recovers** the backend: the consecutive
failure count resets and the score climbs back above the threshold.

All methods are thread-safe.

Slice 6 adds :func:`snapshot`, which merges the monitor's scores and
quarantines with :class:`~hugrgate.circuit.CircuitRegistry` breaker
states and :class:`~hugrgate.fallback.FallbackChain` backend health
into a single per-backend dict.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - annotations only, no runtime cycle
    from hugrgate.circuit import CircuitRegistry
    from hugrgate.fallback import FallbackChain

__all__ = [
    "BackendStats",
    "HealthMonitor",
    "snapshot",
]


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile over an already-sorted list."""
    if not sorted_values:
        return 0.0
    rank = max(1, int(-(-pct * len(sorted_values) // 1)))  # ceil(pct*n)
    return sorted_values[min(rank, len(sorted_values)) - 1]


@dataclass
class BackendStats:
    """Rolling statistics for one backend."""
    latencies: deque[float] = field(default_factory=deque)
    errors: int = 0
    samples: int = 0
    consecutive_failures: int = 0


class HealthMonitor:
    """Track per-backend health; quarantine the sick, recover the healed."""

    def __init__(self, window: int = 100,
                 quarantine_threshold: float = 0.3,
                 max_consecutive_failures: int = 5,
                 latency_target_ms: float = 1000.0,
                 min_samples: int = 3):
        if not 0.0 < quarantine_threshold < 1.0:
            raise ValueError("quarantine_threshold must be in (0,1)")
        self.window = window
        self.quarantine_threshold = quarantine_threshold
        self.max_consecutive_failures = max_consecutive_failures
        self.latency_target_ms = latency_target_ms
        self.min_samples = min_samples
        self._stats: dict[str, BackendStats] = {}
        # RLock: is_quarantined() calls score() while holding the lock.
        self._lock = threading.RLock()

    def _get(self, backend_name: str) -> BackendStats:
        stats = self._stats.get(backend_name)
        if stats is None:
            stats = BackendStats(latencies=deque(maxlen=self.window))
            self._stats[backend_name] = stats
        return stats

    def record(self, backend_name: str, latency_ms: float,
               ok: bool = True) -> None:
        """Record one decision outcome for a backend."""
        with self._lock:
            stats = self._get(backend_name)
            stats.latencies.append(max(0.0, latency_ms))
            stats.samples += 1
            if ok:
                stats.consecutive_failures = 0
            else:
                stats.errors += 1
                stats.consecutive_failures += 1

    def stats(self, backend_name: str) -> dict[str, float]:
        """p50/p99 latency, error rate, consecutive failures, sample count."""
        with self._lock:
            stats = self._stats.get(backend_name)
            if stats is None or not stats.latencies:
                return {"p50_ms": 0.0, "p99_ms": 0.0, "error_rate": 0.0,
                        "consecutive_failures": 0, "samples": 0}
            ordered = sorted(stats.latencies)
            return {
                "p50_ms": _percentile(ordered, 0.50),
                "p99_ms": _percentile(ordered, 0.99),
                "error_rate": stats.errors / stats.samples,
                "consecutive_failures": stats.consecutive_failures,
                "samples": stats.samples,
            }

    def score(self, backend_name: str) -> float:
        """Health score in [0, 1]. Unknown backends score 1.0 (optimistic)."""
        with self._lock:
            stats = self._stats.get(backend_name)
            if stats is None or stats.samples < self.min_samples:
                return 1.0
            ordered = sorted(stats.latencies)
            p50 = _percentile(ordered, 0.50)
            error_rate = stats.errors / stats.samples
            latency_factor = min(1.0, self.latency_target_ms / max(p50, 1e-9))
            return max(0.0, (1.0 - error_rate) * latency_factor)

    def is_quarantined(self, backend_name: str) -> bool:
        """True when the backend should not receive traffic."""
        with self._lock:
            stats = self._stats.get(backend_name)
            if stats is None:
                return False
            if stats.consecutive_failures >= self.max_consecutive_failures:
                return True
            if stats.samples < self.min_samples:
                return False
            return self.score(backend_name) < self.quarantine_threshold

    def quarantined(self) -> list[str]:
        """Names of all currently quarantined backends."""
        with self._lock:
            names = list(self._stats.keys())
        return [n for n in names if self.is_quarantined(n)]

    def reset(self, backend_name: str | None = None) -> None:
        """Forget stats (one backend, or all when no name is given)."""
        with self._lock:
            if backend_name is None:
                self._stats.clear()
            else:
                self._stats.pop(backend_name, None)


def snapshot(monitor: HealthMonitor,
             circuit_registry: CircuitRegistry,
             fallback_chain: FallbackChain) -> dict[str, Any]:
    """Combine the three health sources into one per-backend snapshot.

    For every backend known to *any* of the three sources — the
    :class:`HealthMonitor`, the :class:`~hugrgate.circuit.CircuitRegistry`,
    or the :class:`~hugrgate.fallback.FallbackChain` — the snapshot reports
    the monitor's live score and quarantine state, the circuit breaker's
    current state (``"closed"`` / ``"open"`` / ``"half-open"``), and the
    backend's entry from ``FallbackChain.health()["chain"]``. All values are
    read from the live objects; nothing is invented. Sources that know
    nothing about a backend contribute ``None``.
    """
    circuits = circuit_registry.snapshot()  # name -> breaker snapshot
    chain = fallback_chain.health().get("chain", [])
    chain_health = {entry["backend"]: entry for entry in chain
                    if isinstance(entry, dict) and "backend" in entry}

    with monitor._lock:
        known = list(monitor._stats.keys())
    names: list[str] = []
    for source in (known, circuits, chain_health):
        for name in source:
            if name not in names:
                names.append(name)

    backends: dict[str, dict[str, Any]] = {}
    for name in sorted(names):
        breaker = circuits.get(name)
        backends[name] = {
            "score": monitor.score(name),
            "quarantined": monitor.is_quarantined(name),
            "circuit": breaker["state"] if breaker is not None else None,
            "fallback_health": chain_health.get(name),
        }
    return {
        "backends": backends,
        "quarantined": monitor.quarantined(),
    }
