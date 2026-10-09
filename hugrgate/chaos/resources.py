"""Resource-pressure simulation and guards. Slices 261-262.

The edge layer already sheds load under memory pressure (slice 199's
``memory-pressure`` scenario); the general HugrGate path had no
equivalent. This module provides it:

- :class:`MemoryReading` — a point-in-time memory snapshot with a
  ``pressure_ratio`` (fraction of memory *unavailable*);
- :class:`MemoryPressureSimulator` — scripted readings for
  deterministic tests: ``set_available`` / ``set_pressure_ratio``
  drive the reported memory without touching the real machine;
- :class:`ResourceGuard` — watches a reader callable and escalates
  through ``ok`` → ``warn`` → ``critical`` as pressure crosses
  thresholds. On entering ``warn`` it runs registered shed
  callbacks (best-effort: a raising shedder is logged, never fatal);
  on entering ``critical`` it additionally refuses new work until
  pressure recedes. Transitions are edge-triggered — a sustained
  ``warn`` sheds once, not on every check.

Slice 262 adds CPU-starvation simulation to the same module.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from hugrgate.errors import SpecError
from hugrgate.log import get_logger

logger = get_logger(__name__)

__all__ = [
    "CRITICAL",
    "OK",
    "WARN",
    "MemoryPressureSimulator",
    "MemoryReading",
    "ResourceGuard",
]

#: Guard states.
OK = "ok"
WARN = "warn"
CRITICAL = "critical"


@dataclass(frozen=True)
class MemoryReading:
    """One memory snapshot."""

    total_bytes: int
    available_bytes: int

    def __post_init__(self) -> None:
        if self.total_bytes <= 0:
            raise SpecError(
                f"total_bytes must be > 0, got {self.total_bytes}")
        if not 0 <= self.available_bytes <= self.total_bytes:
            raise SpecError(
                f"available_bytes must be in [0, total_bytes], "
                f"got {self.available_bytes}")

    @property
    def pressure_ratio(self) -> float:
        """Fraction of memory unavailable: 0.0 (empty) → 1.0 (full)."""
        return 1.0 - self.available_bytes / self.total_bytes


class MemoryPressureSimulator:
    """Scripted memory readings for deterministic pressure tests."""

    def __init__(self, total_bytes: int = 8 * 1024**3):
        if total_bytes <= 0:
            raise SpecError(
                f"total_bytes must be > 0, got {total_bytes}")
        self._total = total_bytes
        self._available = total_bytes
        self._lock = threading.RLock()

    def set_available(self, available_bytes: int) -> MemoryPressureSimulator:
        with self._lock:
            if not 0 <= available_bytes <= self._total:
                raise SpecError(
                    f"available_bytes must be in [0, {self._total}], "
                    f"got {available_bytes}")
            self._available = available_bytes
        return self

    def set_pressure_ratio(self, ratio: float) -> MemoryPressureSimulator:
        """Set pressure directly: 0.0 (no pressure) → 1.0 (no memory)."""
        if not 0.0 <= ratio <= 1.0:
            raise SpecError(
                f"pressure ratio must be in [0, 1], got {ratio}")
        # Exact: round the *unavailable* bytes so info().pressure_ratio
        # reads back the requested ratio without float drift.
        return self.set_available(self._total - round(self._total * ratio))

    def info(self) -> MemoryReading:
        """Reader callable for :class:`ResourceGuard`."""
        with self._lock:
            return MemoryReading(self._total, self._available)


class ResourceGuard:
    """Escalate shedding and refusal as memory pressure rises.

    ``warn_ratio`` / ``critical_ratio`` are pressure ratios in
    (0, 1); warn must be below critical. Shed callbacks run when the
    guard *enters* warn or critical; ``allow_work()`` is False while
    critical.
    """

    def __init__(self, reader: Callable[[], MemoryReading],
                 warn_ratio: float = 0.75,
                 critical_ratio: float = 0.9):
        if not 0.0 < warn_ratio < critical_ratio < 1.0:
            raise SpecError(
                f"need 0 < warn_ratio < critical_ratio < 1, got "
                f"{warn_ratio}, {critical_ratio}")
        self._reader = reader
        self._warn_ratio = warn_ratio
        self._critical_ratio = critical_ratio
        self._lock = threading.RLock()
        self._shedders: dict[str, Callable[[], None]] = {}
        self._state = OK
        self._transitions = 0

    # --- shedding ---------------------------------------------------------
    def register_shed(self, name: str,
                      callback: Callable[[], None]) -> ResourceGuard:
        """Register a load-shedding callback run on warn/critical entry."""
        if not name.strip():
            raise SpecError("shedder name must be non-empty")
        with self._lock:
            self._shedders[name] = callback
        return self

    def unregister_shed(self, name: str) -> ResourceGuard:
        with self._lock:
            self._shedders.pop(name, None)
        return self

    # --- state --------------------------------------------------------------
    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def allow_work(self) -> bool:
        """False while critical: new work should be refused."""
        return self.state != CRITICAL

    def transitions(self) -> int:
        with self._lock:
            return self._transitions

    def check(self) -> str:
        """Sample memory, escalate/de-escalate, run shedders on entry.
        Returns the new state."""
        reading = self._reader()
        pressure = reading.pressure_ratio
        if pressure >= self._critical_ratio:
            new_state = CRITICAL
        elif pressure >= self._warn_ratio:
            new_state = WARN
        else:
            new_state = OK
        with self._lock:
            entered = new_state != self._state
            self._state = new_state
            if entered:
                self._transitions += 1
            shedders = list(self._shedders.items())
        if entered and new_state != OK:
            for name, shed in shedders:
                try:
                    shed()
                except Exception as e:  # noqa: BLE001 - best effort
                    logger.warning("resource guard shedder %r failed: %s",
                                   name, e)
        return new_state
