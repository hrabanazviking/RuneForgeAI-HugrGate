"""Node latency scoring. Slice 214.

Round-trip times are measured on every remote RPC and folded into an
exponentially-weighted moving average per peer. The score mirrors the
backend health monitor's latency factor (slice 17):

``score = min(1.0, target_ms / ewma_ms)``

— at or under the target a peer scores 1.0; a peer twice as slow
scores 0.5. Unknown peers score 1.0 (no evidence of slowness).
Percentiles (p50/p95) are exposed for operators and the benchmark
suite (slice 224).
"""

from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass, field

from hugrgate.errors import SpecError

__all__ = [
    "DEFAULT_LATENCY_TARGET_MS",
    "LatencyTracker",
    "PeerLatency",
]

#: RTT at or below this scores a perfect 1.0.
DEFAULT_LATENCY_TARGET_MS = 250.0
#: EWMA smoothing: higher = more weight on recent samples.
DEFAULT_EWMA_ALPHA = 0.3
#: Samples remembered per peer.
DEFAULT_WINDOW = 200


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    rank = max(1, math.ceil(pct * len(sorted_values)))
    return sorted_values[min(rank, len(sorted_values)) - 1]


@dataclass
class PeerLatency:
    """RTT state for one peer."""

    samples: deque[float] = field(default_factory=deque)
    ewma_ms: float = 0.0
    count: int = 0


class LatencyTracker:
    """Per-peer RTT tracking with EWMA scoring. Thread-safe."""

    def __init__(self, target_ms: float = DEFAULT_LATENCY_TARGET_MS,
                 alpha: float = DEFAULT_EWMA_ALPHA,
                 window: int = DEFAULT_WINDOW) -> None:
        if target_ms <= 0:
            raise SpecError("latency target_ms must be > 0")
        if not 0.0 < alpha <= 1.0:
            raise SpecError("ewma alpha must be in (0, 1]")
        if window < 1:
            raise SpecError("latency window must be >= 1")
        self._target_ms = target_ms
        self._alpha = alpha
        self._window = window
        self._peers: dict[str, PeerLatency] = {}
        self._lock = threading.RLock()

    def record(self, node_id: str, rtt_ms: float) -> None:
        """Record one round-trip sample."""
        if (not isinstance(rtt_ms, (int, float))
                or not math.isfinite(rtt_ms) or rtt_ms < 0):
            raise SpecError(
                f"rtt_ms must be a non-negative finite number, got "
                f"{rtt_ms!r}")
        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None:
                peer = PeerLatency()
                self._peers[node_id] = peer
            peer.samples.append(float(rtt_ms))
            if len(peer.samples) > self._window:
                peer.samples.popleft()
            if peer.count == 0:
                peer.ewma_ms = float(rtt_ms)
            else:
                peer.ewma_ms = (self._alpha * float(rtt_ms)
                                + (1.0 - self._alpha) * peer.ewma_ms)
            peer.count += 1

    def ewma(self, node_id: str) -> float:
        with self._lock:
            peer = self._peers.get(node_id)
            return peer.ewma_ms if peer else 0.0

    def percentile(self, node_id: str, pct: float) -> float:
        """p50/p95 over the window (pct in [0, 1])."""
        if not 0.0 <= pct <= 1.0:
            raise SpecError("pct must be in [0, 1]")
        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None:
                return 0.0
            return _percentile(sorted(peer.samples), pct)

    def score(self, node_id: str) -> float:
        """Latency score in [0, 1]; unknown peers score 1.0."""
        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None or peer.count == 0:
                return 1.0
            if peer.ewma_ms <= 0:
                return 1.0
            return min(1.0, self._target_ms / peer.ewma_ms)

    def reset(self, node_id: str) -> None:
        with self._lock:
            self._peers.pop(node_id, None)

    def stats(self, node_id: str) -> dict[str, float | int]:
        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None:
                return {"samples": 0, "ewma_ms": 0.0, "p50_ms": 0.0,
                        "p95_ms": 0.0, "score": 1.0}
            return {"samples": len(peer.samples),
                    "ewma_ms": peer.ewma_ms,
                    "p50_ms": self.percentile(node_id, 0.5),
                    "p95_ms": self.percentile(node_id, 0.95),
                    "score": self.score(node_id)}
