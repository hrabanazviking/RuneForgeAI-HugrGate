"""Edge-tuned decision cache sizing. Slice 190.

The stock :class:`hugrgate.cache.DecisionCache` takes an absolute
``max_size``; on edge boards that number must be *derived* — from the
live memory budget, the board baseline, and the current memory mode.
:func:`tune_cache` computes an :class:`EdgeCacheConfig`; :class:`EdgeCache`
wraps a ``DecisionCache``, applies the config, and re-tunes whenever
:class:`hugrgate.edge.memory.MemoryManager` changes mode (shrinking
the cache on degradation, never growing it without a fresh tune).
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hugrgate.cache import DecisionCache
from hugrgate.edge.memory import MemoryManager, MemoryMode
from hugrgate.edge.platform import EdgeBaseline
from hugrgate.errors import HugrGateError
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "DEFAULT_ENTRY_BYTES",
    "EdgeCache",
    "EdgeCacheConfig",
    "EdgeCacheError",
    "cache_config_for_board",
    "tune_cache",
]

#: Conservative bytes per cache entry (result + key + overhead).
DEFAULT_ENTRY_BYTES = 4096

#: Hard clamps so a wild estimate cannot produce a degenerate cache.
MIN_ENTRIES = 16
MAX_ENTRIES = 100_000

#: TTL multiplier per memory mode.
_MODE_TTL_FACTOR = {
    MemoryMode.STANDARD: 1.0,
    MemoryMode.LOW: 0.5,
    MemoryMode.CRITICAL: 0.25,
}


class EdgeCacheError(HugrGateError):
    """A cache-tuning request was invalid."""


@dataclass(frozen=True)
class EdgeCacheConfig:
    """A derived cache configuration."""

    max_size: int
    ttl_seconds: float
    entry_bytes_estimate: int
    memory_mode: str
    source: str  # "tuned" | "board-baseline"

    def __post_init__(self) -> None:
        if self.max_size < 1:
            raise EdgeCacheError("max_size must be >= 1")
        if self.ttl_seconds <= 0:
            raise EdgeCacheError("ttl_seconds must be > 0")

    def to_dict(self) -> dict[str, Any]:
        return {"max_size": self.max_size, "ttl_seconds": self.ttl_seconds,
                "entry_bytes_estimate": self.entry_bytes_estimate,
                "memory_mode": self.memory_mode, "source": self.source}


def tune_cache(memory: MemoryManager,
               entry_bytes_estimate: int = DEFAULT_ENTRY_BYTES,
               ttl_seconds: float = 300.0) -> EdgeCacheConfig:
    """Derive a cache config from the live memory budget and mode.

    ``max_size`` = (cache-component budget // entry estimate), clamped
    to ``[MIN_ENTRIES, MAX_ENTRIES]``; TTL shrinks with memory pressure
    so stale entries don't pin RAM the system needs back.
    """
    if entry_bytes_estimate <= 0:
        raise EdgeCacheError("entry_bytes_estimate must be > 0")
    if ttl_seconds <= 0:
        raise EdgeCacheError("ttl_seconds must be > 0")
    budget = memory.budget_bytes("cache")
    max_size = budget // entry_bytes_estimate
    max_size = max(MIN_ENTRIES, min(MAX_ENTRIES, max_size))
    ttl = ttl_seconds * _MODE_TTL_FACTOR[memory.mode]
    return EdgeCacheConfig(max_size=int(max_size), ttl_seconds=ttl,
                           entry_bytes_estimate=entry_bytes_estimate,
                           memory_mode=memory.mode.value, source="tuned")


def cache_config_for_board(baseline: EdgeBaseline,
                           ttl_seconds: float = 300.0
                           ) -> EdgeCacheConfig:
    """Static config from a Pi baseline (no live memory manager)."""
    if ttl_seconds <= 0:
        raise EdgeCacheError("ttl_seconds must be > 0")
    return EdgeCacheConfig(
        max_size=max(MIN_ENTRIES,
                     min(MAX_ENTRIES, baseline.recommended_cache_entries)),
        ttl_seconds=ttl_seconds,
        entry_bytes_estimate=DEFAULT_ENTRY_BYTES,
        memory_mode=MemoryMode.STANDARD.value,
        source="board-baseline")


class EdgeCache:
    """A ``DecisionCache`` that re-tunes itself on memory-mode change.

    The wrapped cache is never replaced (callers may hold references);
    instead :meth:`retune` rebuilds it with the new config, preserving
    privacy semantics — entries are dropped, never migrated, because a
    mode change is exactly when RAM must be freed *now*.
    """

    def __init__(self, memory: MemoryManager,
                 entry_bytes_estimate: int = DEFAULT_ENTRY_BYTES,
                 ttl_seconds: float = 300.0):
        self._memory = memory
        self._entry_bytes = entry_bytes_estimate
        self._base_ttl = ttl_seconds
        self._lock = threading.RLock()
        self.config = tune_cache(memory, entry_bytes_estimate, ttl_seconds)
        self.cache = DecisionCache(ttl_seconds=self.config.ttl_seconds,
                                   max_size=self.config.max_size)
        memory.on_mode_change(self._on_mode_change)

    def _on_mode_change(self, old: MemoryMode, new: MemoryMode) -> None:
        self.retune()

    def retune(self) -> EdgeCacheConfig:
        """Re-derive config and rebuild the cache. Returns the config."""
        with self._lock:
            self.config = tune_cache(self._memory, self._entry_bytes,
                                     self._base_ttl)
            self.cache = DecisionCache(ttl_seconds=self.config.ttl_seconds,
                                       max_size=self.config.max_size)
            return self.config

    # -- passthrough API ----------------------------------------------------

    def get(self, state: Mapping[str, Any], spec: DecisionSpec,
            policy: DecisionPolicy) -> DecisionResult | None:
        return self.cache.get(state, spec, policy)

    def put(self, state: Mapping[str, Any], spec: DecisionSpec,
            policy: DecisionPolicy, result: DecisionResult) -> bool:
        return self.cache.put(state, spec, policy, result)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            stats = self.cache.stats()
            stats["config"] = self.config.to_dict()
            return stats
