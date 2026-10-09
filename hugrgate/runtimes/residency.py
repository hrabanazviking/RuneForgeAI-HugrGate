"""Model residency manager. Slice 170.

:func:`ResidencyManager` tracks which models are loaded in which
runtimes and how many live users each has: a ref-counted residency
table with leases.

- :meth:`acquire` loads ``model`` into ``runtime`` when it isn't the
  resident one, bumps the refcount, and returns a
  :class:`ResidencyLease` (a context manager — exiting releases).
- :meth:`release` drops the refcount. A model whose refcount reaches
  zero *stays loaded* (warm cache); only :meth:`evict` unloads it.
  This is the whole point of the fabric: leases track live users,
  eviction tracks VRAM.
- :meth:`evict` force-unloads a runtime regardless of refcount (the
  eviction policy of slice 171 calls this).
- :meth:`touch` refreshes last-use for LRU decisions.

Thread-safe (one ``RLock``). The manager never invents models: it
only tracks what callers asked to load.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any

from hugrgate.runtimes import LocalRuntime, ModelRef

__all__ = [
    "ResidencyEntry",
    "ResidencyLease",
    "ResidencyManager",
]


@dataclass
class ResidencyEntry:
    """One resident model in one runtime."""

    runtime_name: str
    model: ModelRef
    refcount: int = 0
    acquired_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    touches: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_name": self.runtime_name,
            "model": self.model.display,
            "refcount": self.refcount,
            "acquired_at": self.acquired_at,
            "last_used_at": self.last_used_at,
            "touches": self.touches,
        }


class ResidencyLease:
    """Handle returned by :meth:`ResidencyManager.acquire`.

    Exiting the context (or :meth:`release`) returns the lease to the
    manager. Double-release is a no-op.
    """

    def __init__(self, manager: ResidencyManager, runtime_name: str,
                 model: ModelRef) -> None:
        self._manager = manager
        self.runtime_name = runtime_name
        self.model = model
        self._released = False

    def release(self) -> None:
        if not self._released:
            self._released = True
            self._manager.release(self.runtime_name, self.model)

    def __enter__(self) -> ResidencyLease:
        return self

    def __exit__(self, exc_type: type[BaseException] | None,
                 exc: BaseException | None,
                 tb: TracebackType | None) -> None:
        self.release()


class ResidencyManager:
    """Ref-counted table of models loaded in runtimes."""

    def __init__(self) -> None:
        self._entries: dict[str, ResidencyEntry] = {}
        self._unloaders: dict[str, LocalRuntime] = {}
        self._lock = threading.RLock()

    # -- inspection ------------------------------------------------------

    def resident(self, runtime_name: str) -> ResidencyEntry | None:
        with self._lock:
            entry = self._entries.get(runtime_name)
            return entry

    def snapshot(self) -> dict[str, ResidencyEntry]:
        with self._lock:
            return dict(self._entries)

    def is_resident(self, runtime_name: str,
                    model: ModelRef | None = None) -> bool:
        with self._lock:
            entry = self._entries.get(runtime_name)
            if entry is None:
                return False
            return model is None or entry.model == model

    # -- lifecycle --------------------------------------------------------

    def acquire(self, runtime: LocalRuntime,
                model: ModelRef) -> ResidencyLease:
        """Load ``model`` (if not resident) and take one lease on it."""
        self._remember_runtime(runtime)
        with self._lock:
            entry = self._entries.get(runtime.name)
            if entry is not None and entry.model != model:
                # A different model takes over this runtime: unload the
                # old one first so VRAM accounting stays honest.
                self._runtime_unload(runtime.name)
                del self._entries[runtime.name]
                entry = None
            if entry is None:
                runtime.load(model)
                entry = ResidencyEntry(runtime_name=runtime.name,
                                       model=model)
                self._entries[runtime.name] = entry
            entry.refcount += 1
            entry.touches += 1
            entry.last_used_at = time.time()
            return ResidencyLease(self, runtime.name, model)

    def release(self, runtime_name: str, model: ModelRef) -> None:
        """Return one lease.

        The model stays loaded when the refcount reaches zero — it is
        a warm cache entry now, evictable by :meth:`evict` but not
        unloaded by bookkeeping.
        """
        with self._lock:
            entry = self._entries.get(runtime_name)
            if entry is None or entry.model != model:
                return  # stale lease: nothing to do
            entry.refcount = max(0, entry.refcount - 1)
            entry.last_used_at = time.time()

    def touch(self, runtime_name: str) -> None:
        """Refresh last-use timestamp (LRU input)."""
        with self._lock:
            entry = self._entries.get(runtime_name)
            if entry is not None:
                entry.last_used_at = time.time()
                entry.touches += 1

    def evict(self, runtime_name: str) -> ResidencyEntry | None:
        """Force-unload ``runtime_name`` regardless of refcount.

        Returns the evicted entry, or ``None`` when nothing was
        resident. The eviction policy (slice 171) drives this.
        """
        with self._lock:
            entry = self._entries.pop(runtime_name, None)
            if entry is None:
                return None
            try:
                self._runtime_unload(runtime_name)
            except Exception:  # noqa: BLE001 - eviction is best-effort
                pass
            return entry

    # -- internals ---------------------------------------------------------

    def _runtime_unload(self, runtime_name: str) -> None:
        runtime = self._unloaders.get(runtime_name)
        if runtime is not None:
            runtime.unload()

    def _remember_runtime(self, runtime: LocalRuntime) -> None:
        self._unloaders[runtime.name] = runtime
