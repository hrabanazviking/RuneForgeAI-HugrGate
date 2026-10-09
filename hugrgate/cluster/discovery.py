"""Node discovery — finding peers. Slice 204.

Discovery is a *framework*, not a mechanism: :class:`Discovery` is the
adapter interface, and :class:`DiscoveryRegistry` merges every
configured adapter (static files in slice 205, LAN multicast in slice
206, …) into one deduplicated, staleness-pruned peer table.

A peer is identified by its ``node_id``; the same node seen by two
adapters collapses to one :class:`PeerRecord`, newest ``last_seen``
wins. Records older than ``stale_after_s`` are pruned on read — a peer
nobody has heard from is not a peer, it is a memory.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from hugrgate.cluster.capabilities import NodeCapabilities
from hugrgate.errors import SpecError

__all__ = [
    "DEFAULT_STALE_AFTER_S",
    "Discovery",
    "DiscoveryRegistry",
    "PeerRecord",
]

#: Peers unheard-from for this long are dropped from the table.
DEFAULT_STALE_AFTER_S = 60.0


@dataclass
class PeerRecord:
    """One known peer."""

    node_id: str
    host: str
    port: int
    last_seen: float = field(default_factory=time.time)
    capabilities: NodeCapabilities | None = None
    source: str = "unknown"       # which adapter reported it
    tls: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or not self.node_id:
            raise SpecError("peer needs a non-empty node_id")
        if not isinstance(self.host, str) or not self.host:
            raise SpecError("peer needs a non-empty host")
        if not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise SpecError(f"peer port out of range: {self.port!r}")

    @property
    def address(self) -> str:
        scheme = "https" if self.tls else "http"
        return f"{scheme}://{self.host}:{self.port}"

    def age_s(self, now: float | None = None) -> float:
        return (time.time() if now is None else now) - self.last_seen

    def is_stale(self, stale_after_s: float = DEFAULT_STALE_AFTER_S,
                 now: float | None = None) -> bool:
        return self.age_s(now) > stale_after_s

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "host": self.host,
            "port": self.port,
            "last_seen": self.last_seen,
            "capabilities": (self.capabilities.to_dict()
                             if self.capabilities else None),
            "source": self.source,
            "tls": self.tls,
        }


class Discovery(ABC):
    """One mechanism for finding peers. Adapters are cheap to write:

    subclass, implement :meth:`peers`, optionally override
    :meth:`start`/:meth:`stop` for background listening.
    """

    #: Human name used as ``PeerRecord.source``.
    name: str = "discovery"

    def start(self) -> None:  # noqa: B027 - intentional no-op hook
        """Begin background discovery (no-op for pull-style adapters)."""

    def stop(self) -> None:  # noqa: B027 - intentional no-op hook
        """Halt background discovery (no-op for pull-style adapters)."""

    @abstractmethod
    def peers(self) -> list[PeerRecord]:
        """Currently known peers from this adapter."""

    def __enter__(self) -> Discovery:
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.stop()


class DiscoveryRegistry:
    """Merges adapters into one peer table.

    Thread-safe. Deduplicates by ``node_id`` (newest ``last_seen``
    wins); :meth:`peers` prunes records older than ``stale_after_s``.
    The local node is never listed as its own peer.
    """

    def __init__(self, local_node_id: str = "",
                 stale_after_s: float = DEFAULT_STALE_AFTER_S) -> None:
        if stale_after_s <= 0:
            raise SpecError("stale_after_s must be > 0")
        self._local_node_id = local_node_id
        self._stale_after_s = stale_after_s
        self._adapters: list[Discovery] = []
        self._lock = threading.RLock()

    def add_adapter(self, adapter: Discovery) -> None:
        if not isinstance(adapter, Discovery):
            raise SpecError(
                f"adapter must be a Discovery, got {type(adapter).__name__}")
        with self._lock:
            self._adapters.append(adapter)

    def start_all(self) -> None:
        with self._lock:
            adapters = list(self._adapters)
        for adapter in adapters:
            adapter.start()

    def stop_all(self) -> None:
        with self._lock:
            adapters = list(self._adapters)
        for adapter in adapters:
            adapter.stop()

    def peers(self) -> list[PeerRecord]:
        """Deduplicated, staleness-pruned peers, freshest first."""
        now = time.time()
        merged: dict[str, PeerRecord] = {}
        with self._lock:
            adapters = list(self._adapters)
        for adapter in adapters:
            try:
                found = adapter.peers()
            except Exception:  # noqa: BLE001 - one bad adapter must not
                # blind the node to every other adapter's peers
                continue
            for peer in found:
                if peer.node_id == self._local_node_id:
                    continue  # never peer with ourselves
                if peer.is_stale(self._stale_after_s, now):
                    continue
                current = merged.get(peer.node_id)
                if current is None or peer.last_seen > current.last_seen:
                    merged[peer.node_id] = peer
        return sorted(merged.values(),
                      key=lambda p: p.last_seen, reverse=True)

    def find(self, node_id: str) -> PeerRecord | None:
        for peer in self.peers():
            if peer.node_id == node_id:
                return peer
        return None

    def __len__(self) -> int:
        return len(self.peers())
