"""Power-budget routing for edge deployment. Slice 181.

:class:`PowerBudget` is a ledger of milliwatts: a fixed budget (minus a
safety reserve), named consumers, and a feasibility check that the
edge router (:mod:`hugrgate.edge.routing`) uses to keep backend
selection inside the device's power envelope. :class:`PowerSource`
abstracts live power telemetry (sysfs hwmon or an injected mock);
without a source the budget runs *open-loop* on declared backend costs,
which is honest about its uncertainty in :meth:`PowerBudget.to_dict`.
"""

from __future__ import annotations

import glob
import threading
from abc import ABC, abstractmethod
from typing import Any

from hugrgate.errors import HugrGateError

__all__ = [
    "MockPowerSource",
    "PowerBudget",
    "PowerBudgetError",
    "PowerSource",
    "SysfsPowerSensor",
]


class PowerBudgetError(HugrGateError):
    """A power-budget invariant was violated."""


class PowerSource(ABC):
    """Live power telemetry source."""

    @abstractmethod
    def read_mw(self) -> float | None:
        """Current system power draw in milliwatts, or None if unreadable."""


class SysfsPowerSensor(PowerSource):
    """Reads a sysfs power file (microwatts or milliwatts).

    ``path_glob`` is injectable for tests; the first readable file
    wins. Values above 1e6 are assumed to be microwatts.
    """

    def __init__(self, path_glob: str = "/sys/class/hwmon/hwmon*/power1_input"):
        self.path_glob = path_glob

    def read_mw(self) -> float | None:
        for path in sorted(glob.glob(self.path_glob)):
            try:
                with open(path, encoding="utf-8") as fh:
                    value = float(fh.read().strip())
            except (OSError, ValueError):
                continue
            return value / 1000.0 if value > 1e6 else value
        return None


class MockPowerSource(PowerSource):
    """Scripted power readings; holds the last value when exhausted."""

    def __init__(self, script: list[float | None]):
        if not script:
            raise ValueError("power script must not be empty")
        self._script = list(script)
        self._index = 0

    def read_mw(self) -> float | None:
        value = self._script[min(self._index, len(self._script) - 1)]
        self._index += 1
        return value


class PowerBudget:
    """Milliwatt ledger with a safety reserve and feasibility checks."""

    def __init__(self, budget_mw: float, reserve_mw: float = 0.0,
                 source: PowerSource | None = None):
        if budget_mw <= 0:
            raise PowerBudgetError("budget_mw must be > 0")
        if not 0 <= reserve_mw < budget_mw:
            raise PowerBudgetError(
                "reserve_mw must satisfy 0 <= reserve_mw < budget_mw")
        self._budget_mw = float(budget_mw)
        self._reserve_mw = float(reserve_mw)
        self._source = source
        self._lock = threading.RLock()
        self._consumers: dict[str, float] = {}

    @property
    def budget_mw(self) -> float:
        return self._budget_mw

    @property
    def reserve_mw(self) -> float:
        return self._reserve_mw

    def register_consumer(self, name: str, power_mw: float) -> None:
        """Book a named consumer; raises if it alone exceeds the budget."""
        if power_mw < 0:
            raise PowerBudgetError("consumer power must be >= 0")
        with self._lock:
            if name in self._consumers:
                raise PowerBudgetError(
                    f"consumer {name!r} already registered")
            if power_mw > self._budget_mw - self._reserve_mw:
                raise PowerBudgetError(
                    f"consumer {name!r} ({power_mw} mW) exceeds usable "
                    f"budget {self._budget_mw - self._reserve_mw} mW")
            self._consumers[name] = float(power_mw)

    def deregister_consumer(self, name: str) -> float:
        """Remove a consumer; returns its booked power (0.0 if absent)."""
        with self._lock:
            return self._consumers.pop(name, 0.0)

    def committed_mw(self) -> float:
        with self._lock:
            return sum(self._consumers.values())

    def remaining_mw(self) -> float:
        """Usable budget minus committed consumers (never negative)."""
        return max(0.0, self._budget_mw - self._reserve_mw
                   - self.committed_mw())

    def live_draw_mw(self) -> float | None:
        """Live telemetry when a source is attached, else None."""
        return self._source.read_mw() if self._source else None

    def feasible(self, power_mw: float) -> bool:
        """True when a ``power_mw`` consumer fits in the remaining budget."""
        if power_mw < 0:
            raise PowerBudgetError("power_mw must be >= 0")
        return power_mw <= self.remaining_mw()

    def utilization(self) -> float:
        """Committed fraction of the usable budget, in [0, 1]."""
        usable = self._budget_mw - self._reserve_mw
        return min(1.0, self.committed_mw() / usable)

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "budget_mw": self._budget_mw,
                "reserve_mw": self._reserve_mw,
                "committed_mw": self.committed_mw(),
                "remaining_mw": self.remaining_mw(),
                "utilization": self.utilization(),
                "consumers": dict(self._consumers),
                "live_draw_mw": self.live_draw_mw(),
                "open_loop": self._source is None,
            }
