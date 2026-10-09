"""Edge model residency management. Slice 189.

:class:`ResidencyManager` decides which models live in RAM right now.
It keeps a catalog of known models (name → size), a set of resident
models with reference counts, and an LRU eviction policy bounded by a
byte budget. Pinned models (the active voice model, the safety
classifier) are never evicted. The manager subscribes to
:class:`hugrgate.edge.memory.MemoryManager` mode changes: when memory
degrades to ``low`` it sheds every unpinned idle model; in
``critical`` it additionally refuses new non-pinned acquisitions —
better to abstain than to OOM mid-decision.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from hugrgate.edge.memory import MemoryManager, MemoryMode
from hugrgate.errors import HugrGateError

__all__ = [
    "ModelEntry",
    "ResidencyError",
    "ResidencyManager",
]


class ResidencyError(HugrGateError):
    """A residency invariant was violated (unknown model, no room)."""


@dataclass
class ModelEntry:
    """Catalog record for one loadable model."""

    name: str
    size_bytes: int
    profile: str = "fp32"      # QuantProfile name (slice 182)
    pinned: bool = False
    resident: bool = False
    refcount: int = 0
    last_used: float = 0.0      # monotonic seconds of last release
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ResidencyError("model name must be non-empty")
        if self.size_bytes <= 0:
            raise ResidencyError("model size_bytes must be > 0")


class ResidencyManager:
    """LRU model residency under a byte budget, memory-mode aware."""

    def __init__(self, ram_budget_bytes: int,
                 memory: MemoryManager | None = None,
                 clock: Any | None = None):
        if ram_budget_bytes <= 0:
            raise ResidencyError("ram_budget_bytes must be > 0")
        self._budget = int(ram_budget_bytes)
        self._memory = memory
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._models: dict[str, ModelEntry] = {}
        self._resident_bytes = 0
        if memory is not None:
            memory.on_mode_change(self._on_memory_mode)

    # -- catalog ------------------------------------------------------------

    def register_model(self, entry: ModelEntry) -> None:
        if not isinstance(entry, ModelEntry):
            raise ResidencyError(
                f"can only register ModelEntry, got "
                f"{type(entry).__name__}")
        with self._lock:
            if entry.name in self._models:
                raise ResidencyError(
                    f"model {entry.name!r} already registered")
            if entry.size_bytes > self._budget:
                raise ResidencyError(
                    f"model {entry.name!r} ({entry.size_bytes} bytes) "
                    f"can never fit in budget {self._budget}")
            self._models[entry.name] = entry

    def pin(self, name: str) -> None:
        with self._lock:
            self._entry(name).pinned = True

    def unpin(self, name: str) -> None:
        with self._lock:
            self._entry(name).pinned = False

    def _entry(self, name: str) -> ModelEntry:
        try:
            return self._models[name]
        except KeyError:
            raise ResidencyError(f"unknown model {name!r}") from None

    # -- residency ------------------------------------------------------------

    def _used_bytes(self) -> int:
        return self._resident_bytes

    def acquire(self, name: str) -> ModelEntry:
        """Make ``name`` resident (loading it, evicting LRU if needed).

        Increments the refcount; the caller must :meth:`release`.
        Raises :class:`ResidencyError` when the model cannot be made
        to fit, or when memory mode is critical and the model is not
        pinned.
        """
        with self._lock:
            entry = self._entry(name)
            if entry.resident:
                entry.refcount += 1
                return entry
            if (self._memory is not None
                    and self._memory.mode is MemoryMode.CRITICAL
                    and not entry.pinned):
                raise ResidencyError(
                    f"memory critical: refusing non-pinned model {name!r}")
            self._make_room(entry.size_bytes)
            entry.resident = True
            entry.refcount = 1
            self._resident_bytes += entry.size_bytes
            return entry

    def release(self, name: str) -> None:
        """Decrement the refcount; stamps last_used at zero."""
        with self._lock:
            entry = self._entry(name)
            if not entry.resident or entry.refcount <= 0:
                raise ResidencyError(
                    f"model {name!r} is not acquired")
            entry.refcount -= 1
            if entry.refcount == 0:
                entry.last_used = self._clock()

    def _make_room(self, need_bytes: int) -> None:
        """Evict LRU unpinned idle models until ``need_bytes`` fits."""
        while (self._used_bytes() + need_bytes > self._budget):
            victim = self._lru_victim()
            if victim is None:
                raise ResidencyError(
                    f"no evictable model frees {need_bytes} bytes "
                    f"(budget {self._budget}, used {self._used_bytes()})")
            self._evict(victim)

    def _lru_victim(self) -> ModelEntry | None:
        candidates = [e for e in self._models.values()
                      if e.resident and not e.pinned and e.refcount == 0]
        if not candidates:
            return None
        return min(candidates, key=lambda e: e.last_used)

    def _evict(self, entry: ModelEntry) -> None:
        entry.resident = False
        self._resident_bytes -= entry.size_bytes

    def evict_idle(self) -> list[str]:
        """Evict every unpinned idle model; returns evicted names."""
        with self._lock:
            evicted = []
            while True:
                victim = self._lru_victim()
                if victim is None:
                    break
                self._evict(victim)
                evicted.append(victim.name)
            return evicted

    # -- memory-mode reaction ----------------------------------------------------

    def _on_memory_mode(self, old: MemoryMode, new: MemoryMode) -> None:
        # Any degradation sheds idle weight immediately; recovery does
        # not auto-reload (the next acquire() does that on demand).
        if new is not MemoryMode.STANDARD:
            self.evict_idle()

    # -- introspection -----------------------------------------------------------------

    def resident_models(self) -> list[str]:
        with self._lock:
            return sorted(n for n, e in self._models.items() if e.resident)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "budget_bytes": self._budget,
                "used_bytes": self._resident_bytes,
                "free_bytes": self._budget - self._resident_bytes,
                "resident": self.resident_models(),
                "models": {
                    n: {"size_bytes": e.size_bytes, "profile": e.profile,
                        "pinned": e.pinned, "resident": e.resident,
                        "refcount": e.refcount}
                    for n, e in self._models.items()
                },
            }
