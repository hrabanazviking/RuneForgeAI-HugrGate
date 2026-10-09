"""Network partition handling. Slice 219.

When the network splits, the minority side must not keep serving and
routing as if nothing happened — that's how split-brain writes and
phantom decisions happen. :class:`PartitionDetector` tracks peer
liveness from heartbeats and answers one question: *can this node see
a majority of the cluster?*

``has_quorum(peer_ids)`` — ``(live + 1) * 2 > (known + 1)`` (the +1 is
this node, which counts itself alive). A lone node is its own
majority; two nodes with one dark is not.

Fail-closed policy (opt-in via ``ClusterNode(enforce_quorum=True)``,
following the codebase's convention of permissive defaults with
explicit strictness like ``require_auth``): without quorum the node

- refuses inbound work-plane messages (``BackendUnavailable``,
  "no quorum"),
- routes local-only (remote candidates vanish from the ladder),
- refuses direct ``decide_remote`` calls.

Local decisions continue — a partitioned node still answers for
itself, it just stops speaking for the cluster. Heartbeats ride the
existing ``HEARTBEAT`` message type (control plane, never shed by
slice 218's admission control).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Collection

from hugrgate.errors import SpecError

__all__ = [
    "DEFAULT_PARTITION_STALE_AFTER_S",
    "PartitionDetector",
]

#: A peer unseen for this long counts as dark.
DEFAULT_PARTITION_STALE_AFTER_S = 30.0


class PartitionDetector:
    """Heartbeat-driven liveness and quorum. Thread-safe."""

    def __init__(self, stale_after_s: float = DEFAULT_PARTITION_STALE_AFTER_S,
                 clock: Callable[[], float] | None = None) -> None:
        if stale_after_s <= 0:
            raise SpecError("stale_after_s must be > 0")
        self._stale_after_s = stale_after_s
        self._clock = clock or time.monotonic
        self._last_seen: dict[str, float] = {}
        self._lock = threading.RLock()

    @property
    def stale_after_s(self) -> float:
        return self._stale_after_s

    def note_heartbeat(self, node_id: str) -> None:
        """Record that a peer is alive right now."""
        with self._lock:
            self._last_seen[node_id] = self._clock()

    def last_seen(self, node_id: str) -> float | None:
        """Monotonic timestamp of the last heartbeat, if any."""
        with self._lock:
            return self._last_seen.get(node_id)

    def is_live(self, node_id: str) -> bool:
        """True when a recent heartbeat is on record."""
        with self._lock:
            seen = self._last_seen.get(node_id)
            if seen is None:
                return False
            return self._clock() - seen <= self._stale_after_s

    def live_peers(self, peer_ids: Collection[str]) -> list[str]:
        """The subset of ``peer_ids`` currently live."""
        return [nid for nid in peer_ids if self.is_live(nid)]

    def has_quorum(self, peer_ids: Collection[str]) -> bool:
        """True when this node can see a strict majority.

        ``peer_ids`` are the known *other* nodes; this node counts
        itself as the +1 on both sides. Empty cluster: a lone node is
        its own majority.
        """
        known = set(peer_ids)
        total = len(known) + 1
        live = len(self.live_peers(known)) + 1
        return live * 2 > total

    def forget(self, node_id: str) -> None:
        """Drop liveness state (the peer left cleanly)."""
        with self._lock:
            self._last_seen.pop(node_id, None)
