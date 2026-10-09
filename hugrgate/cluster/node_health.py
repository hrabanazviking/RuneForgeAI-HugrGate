"""Node health scoring. Slice 213.

Mirrors the backend :class:`HealthMonitor` (slice 17) at node scope:
every remote RPC outcome is recorded, and each peer gets a score in
[0, 1] from its recent window:

``score = 1 - failures/window``

with an empty window scoring 1.0 (no evidence of sickness — optimism
with a fast quarantine). A peer is **quarantined** when its score
drops below ``quarantine_threshold`` or ``max_consecutive_failures``
strike in a row; a single success resets the consecutive count, so
recovery is automatic. The router (slice 212) reads these scores via
``node.refresh_scores()``; quarantined peers score 0.0 and sink to the
bottom of every route.

Thread-safe. Only transport/backend failures count — an ``Abstention``
is a successful RPC that decided "I don't know", not sickness.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field

from hugrgate.errors import SpecError

__all__ = [
    "DEFAULT_QUARANTINE_THRESHOLD",
    "NodeHealthMonitor",
    "PeerHealth",
]

#: Score below this → quarantined.
DEFAULT_QUARANTINE_THRESHOLD = 0.5
#: Consecutive failures that force quarantine regardless of window.
DEFAULT_MAX_CONSECUTIVE_FAILURES = 5
#: Outcomes remembered per peer.
DEFAULT_WINDOW = 100


@dataclass
class PeerHealth:
    """Rolling health for one peer."""

    outcomes: deque[bool] = field(default_factory=deque)
    consecutive_failures: int = 0
    total_successes: int = 0
    total_failures: int = 0


class NodeHealthMonitor:
    """Track per-peer RPC health; quarantine the sick."""

    def __init__(self, window: int = DEFAULT_WINDOW,
                 quarantine_threshold: float = (
                     DEFAULT_QUARANTINE_THRESHOLD),
                 max_consecutive_failures: int = (
                     DEFAULT_MAX_CONSECUTIVE_FAILURES)) -> None:
        if window < 1:
            raise SpecError("health window must be >= 1")
        if not 0.0 <= quarantine_threshold <= 1.0:
            raise SpecError("quarantine_threshold must be in [0, 1]")
        if max_consecutive_failures < 1:
            raise SpecError("max_consecutive_failures must be >= 1")
        self._window = window
        self._threshold = quarantine_threshold
        self._max_consecutive = max_consecutive_failures
        self._peers: dict[str, PeerHealth] = {}
        self._lock = threading.RLock()

    def _get(self, node_id: str) -> PeerHealth:
        peer = self._peers.get(node_id)
        if peer is None:
            peer = PeerHealth()
            self._peers[node_id] = peer
        return peer

    def record_success(self, node_id: str) -> None:
        with self._lock:
            peer = self._get(node_id)
            peer.outcomes.append(True)
            if len(peer.outcomes) > self._window:
                peer.outcomes.popleft()
            peer.consecutive_failures = 0
            peer.total_successes += 1

    def record_failure(self, node_id: str) -> None:
        with self._lock:
            peer = self._get(node_id)
            peer.outcomes.append(False)
            if len(peer.outcomes) > self._window:
                peer.outcomes.popleft()
            peer.consecutive_failures += 1
            peer.total_failures += 1

    def score(self, node_id: str) -> float:
        """Health in [0, 1]; quarantined peers score 0.0."""
        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None or not peer.outcomes:
                return 1.0  # no evidence of sickness
            if self._is_quarantined_locked(peer):
                return 0.0
            failures = sum(1 for ok in peer.outcomes if not ok)
            return 1.0 - failures / len(peer.outcomes)

    def _is_quarantined_locked(self, peer: PeerHealth) -> bool:
        if peer.consecutive_failures >= self._max_consecutive:
            return True
        if not peer.outcomes:
            return False
        failures = sum(1 for ok in peer.outcomes if not ok)
        return (1.0 - failures / len(peer.outcomes)) < self._threshold

    def is_quarantined(self, node_id: str) -> bool:
        with self._lock:
            peer = self._peers.get(node_id)
            return peer is not None and self._is_quarantined_locked(peer)

    def quarantined_peers(self) -> list[str]:
        with self._lock:
            return [nid for nid, peer in self._peers.items()
                    if self._is_quarantined_locked(peer)]

    def reset(self, node_id: str) -> None:
        """Forget everything about a peer (it rejoined clean, slice 220)."""
        with self._lock:
            self._peers.pop(node_id, None)

    def stats(self, node_id: str) -> dict[str, float | int | bool]:
        with self._lock:
            peer = self._peers.get(node_id)
            if peer is None:
                return {"samples": 0, "score": 1.0,
                        "quarantined": False,
                        "consecutive_failures": 0}
            return {"samples": len(peer.outcomes),
                    "score": self.score(node_id),
                    "quarantined": self._is_quarantined_locked(peer),
                    "consecutive_failures": peer.consecutive_failures,
                    "total_successes": peer.total_successes,
                    "total_failures": peer.total_failures}
