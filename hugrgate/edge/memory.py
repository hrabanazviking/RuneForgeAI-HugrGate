"""Low-RAM operating modes for edge deployment. Slice 178.

:class:`MemoryManager` keeps one global view of host memory (parsed from
``/proc/meminfo``, honoring cgroup v1/v2 limits when present), derives a
:class:`MemoryMode` (``standard`` / ``low`` / ``critical``) from the
available headroom, and enforces per-component byte budgets with an
alloc/release ledger. Components that can shed load (caches, model
residency) register ``on_mode_change`` callbacks and are told —
deterministically, in registration order — when the mode degrades or
recovers.

All reads are injectable so the whole state machine is testable on a
memory-rich CI host.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from hugrgate.errors import HugrGateError

__all__ = [
    "EdgeMemoryError",
    "MemoryInfo",
    "MemoryManager",
    "MemoryMode",
]

#: Available-memory thresholds (bytes) for mode derivation.
CRITICAL_AVAILABLE_BYTES = 256 * 1024 * 1024
LOW_AVAILABLE_BYTES = 1024 * 1024 * 1024

#: Per-mode fractional budgets: how much of available RAM each
#: subsystem may claim. Fractions sum below 1.0 so the OS keeps air.
_MODE_BUDGETS: dict[str, dict[str, float]] = {
    "standard": {"models": 0.50, "cache": 0.15, "telemetry": 0.05,
                 "working": 0.20},
    "low": {"models": 0.40, "cache": 0.06, "telemetry": 0.02,
            "working": 0.15},
    "critical": {"models": 0.25, "cache": 0.02, "telemetry": 0.01,
                 "working": 0.08},
}


class MemoryMode(str, Enum):
    """Operating mode derived from available memory headroom."""

    STANDARD = "standard"
    LOW = "low"
    CRITICAL = "critical"


class EdgeMemoryError(HugrGateError):
    """A memory budget was exceeded or an allocation was invalid."""


@dataclass(frozen=True)
class MemoryInfo:
    """Snapshot of host memory relevant to the mode state machine."""

    total_bytes: int
    available_bytes: int
    cgroup_limited: bool
    live: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"total_bytes": self.total_bytes,
                "available_bytes": self.available_bytes,
                "cgroup_limited": self.cgroup_limited,
                "live": self.live}


def _parse_meminfo_kb(text: str, key: str) -> int | None:
    for line in text.splitlines():
        head, sep, rest = line.partition(":")
        if sep and head.strip() == key:
            parts = rest.strip().split()
            if parts and parts[0].isdigit():
                return int(parts[0])
    return None


class MemoryManager:
    """Owns the edge memory-mode state machine and the byte ledger."""

    def __init__(self, meminfo_text: str | None = None,
                 cgroup_limit_bytes: int | None = None):
        # None -> read the live host; values -> fixtures (live=False).
        self._meminfo_text = meminfo_text
        self._cgroup_limit = cgroup_limit_bytes
        self._lock = threading.RLock()
        self._mode = MemoryMode.STANDARD
        self._callbacks: list[Callable[[MemoryMode, MemoryMode], None]] = []
        self._ledger: dict[str, int] = {}

    # -- probing -----------------------------------------------------------

    def _read_meminfo(self) -> tuple[str, bool]:
        if self._meminfo_text is not None:
            return self._meminfo_text, False
        try:
            with open("/proc/meminfo", encoding="utf-8") as fh:
                return fh.read(), True
        except OSError:
            return "", True

    def probe(self) -> MemoryInfo:
        text, live = self._read_meminfo()
        total_kb = _parse_meminfo_kb(text, "MemTotal") or 0
        avail_kb = _parse_meminfo_kb(text, "MemAvailable")
        if avail_kb is None:  # ancient kernels lack MemAvailable
            free_kb = _parse_meminfo_kb(text, "MemFree") or 0
            buffers_kb = _parse_meminfo_kb(text, "Buffers") or 0
            cached_kb = _parse_meminfo_kb(text, "Cached") or 0
            avail_kb = free_kb + buffers_kb + cached_kb
        total = total_kb * 1024
        if self._cgroup_limit is not None:
            total = min(total, self._cgroup_limit)
        return MemoryInfo(total_bytes=total,
                          available_bytes=avail_kb * 1024,
                          cgroup_limited=self._cgroup_limit is not None,
                          live=live)

    # -- mode state machine -------------------------------------------------

    @staticmethod
    def mode_for(available_bytes: int) -> MemoryMode:
        if available_bytes < CRITICAL_AVAILABLE_BYTES:
            return MemoryMode.CRITICAL
        if available_bytes < LOW_AVAILABLE_BYTES:
            return MemoryMode.LOW
        return MemoryMode.STANDARD

    @property
    def mode(self) -> MemoryMode:
        with self._lock:
            return self._mode

    def on_mode_change(self, callback: Callable[[MemoryMode, MemoryMode],
                                                None]) -> None:
        """Register ``callback(old, new)``; called in registration order."""
        with self._lock:
            self._callbacks.append(callback)

    def refresh(self, info: MemoryInfo | None = None) -> MemoryMode:
        """Re-probe, derive the mode, notify on change. Returns the mode."""
        info = info or self.probe()
        new_mode = self.mode_for(info.available_bytes)
        with self._lock:
            old_mode = self._mode
            callbacks = list(self._callbacks)
            if new_mode != old_mode:
                self._mode = new_mode
        if new_mode != old_mode:
            for cb in callbacks:
                cb(old_mode, new_mode)
        return new_mode

    # -- budgets -------------------------------------------------------------

    def budget_bytes(self, component: str,
                     info: MemoryInfo | None = None) -> int:
        """Byte budget for ``component`` under the current mode."""
        fractions = _MODE_BUDGETS[self.mode.value]
        if component not in fractions:
            raise EdgeMemoryError(
                f"unknown memory component {component!r}; known: "
                f"{sorted(fractions)}")
        info = info or self.probe()
        return int(info.available_bytes * fractions[component])

    def budgets(self, info: MemoryInfo | None = None) -> dict[str, int]:
        info = info or self.probe()
        return {c: self.budget_bytes(c, info)
                for c in _MODE_BUDGETS[self.mode.value]}

    # -- allocation ledger ----------------------------------------------------

    def allocate(self, component: str, name: str, nbytes: int) -> None:
        """Claim ``nbytes`` for ``component``; raises over budget."""
        if nbytes < 0:
            raise EdgeMemoryError("allocation size must be >= 0")
        budget = self.budget_bytes(component)
        with self._lock:
            used = sum(v for k, v in self._ledger.items()
                       if k.startswith(component + "/"))
            if used + nbytes > budget:
                raise EdgeMemoryError(
                    f"{component} over budget: {used + nbytes} > {budget} "
                    f"bytes in {self.mode.value} mode")
            key = f"{component}/{name}"
            if key in self._ledger:
                raise EdgeMemoryError(f"duplicate allocation {key!r}")
            self._ledger[key] = nbytes

    def release(self, component: str, name: str) -> int:
        """Release a claim; returns the bytes freed (0 if absent)."""
        with self._lock:
            return self._ledger.pop(f"{component}/{name}", 0)

    def ledger(self) -> Mapping[str, int]:
        with self._lock:
            return dict(self._ledger)

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {"mode": self.mode.value,
                    "ledger": dict(self._ledger)}
