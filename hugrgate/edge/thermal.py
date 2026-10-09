"""Thermal sensing and thermal-aware derating. Slice 180.

:class:`ThermalSensor` abstracts the SoC temperature source (Linux
thermal sysfs zones, or an injected mock for tests and CI).
:class:`ThermalGovernor` turns readings into a hysteresis-guarded
:class:`ThermalLevel` plus a derating factor that the edge router
(:mod:`hugrgate.edge.routing`) uses to shed hot backends before the
silicon does it for us.

Thresholds default to Raspberry Pi-ish figures (warn 70 °C, critical
85 °C) and are fully configurable; on-device tuning is marked
``NEEDS_HARDWARE_VALIDATION`` in the slice doc.
"""

from __future__ import annotations

import glob
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = [
    "CRITICAL_C",
    "WARN_C",
    "MockThermalSensor",
    "SysfsThermalSensor",
    "ThermalGovernor",
    "ThermalLevel",
    "ThermalSensor",
    "ThermalState",
]

#: Default thresholds (°C). Pi 4/5 throttle near 80-85 °C.
WARN_C = 70.0
CRITICAL_C = 85.0
#: Hysteresis margin (°C): a level only clears when temp drops this far
#: below its entry threshold, preventing routing flaps at the boundary.
HYSTERESIS_C = 3.0


class ThermalLevel(str, Enum):
    """Governor output level; ordered cool -> critical."""

    NORMAL = "normal"
    WARM = "warm"
    HOT = "hot"
    CRITICAL = "critical"

    @property
    def derating(self) -> float:
        """Fraction of nominal inference throughput to schedule."""
        return {"normal": 1.0, "warm": 0.75,
                "hot": 0.5, "critical": 0.25}[self.value]


class ThermalSensor(ABC):
    """Source of SoC temperature readings."""

    @abstractmethod
    def read_celsius(self) -> float | None:
        """Current temperature, or None when the sensor is unreadable."""


class SysfsThermalSensor(ThermalSensor):
    """Reads Linux ``/sys/class/thermal/thermal_zone*/temp``.

    ``zone_glob`` is injectable so tests can point at fixture trees.
    Takes the *maximum* across zones (the hottest zone governs).
    """

    def __init__(self, zone_glob: str = "/sys/class/thermal/thermal_zone*"):
        self.zone_glob = zone_glob

    def read_celsius(self) -> float | None:
        hottest: float | None = None
        for zone in sorted(glob.glob(self.zone_glob)):
            try:
                with open(f"{zone}/temp", encoding="utf-8") as fh:
                    raw = fh.read().strip()
                # sysfs reports millidegrees; tolerate plain degrees.
                value = float(raw)
                celsius = value / 1000.0 if value > 200 else value
            except (OSError, ValueError):
                continue
            hottest = celsius if hottest is None else max(hottest, celsius)
        return hottest


class MockThermalSensor(ThermalSensor):
    """Scripted sensor for tests: yields the script, then holds last."""

    def __init__(self, script: list[float | None]):
        if not script:
            raise ValueError("thermal script must not be empty")
        self._script = list(script)
        self._index = 0

    def read_celsius(self) -> float | None:
        value = self._script[min(self._index, len(self._script) - 1)]
        self._index += 1
        return value


@dataclass(frozen=True)
class ThermalState:
    """One governor decision: reading, level, and routing derating."""

    temp_c: float | None
    level: ThermalLevel
    derating: float

    def to_dict(self) -> dict[str, Any]:
        return {"temp_c": self.temp_c, "level": self.level.value,
                "derating": self.derating}


class ThermalGovernor:
    """Hysteresis-guarded thermal level machine.

    Levels only step *up* when the reading crosses the entry threshold
    and only step *down* when it falls below threshold minus
    ``HYSTERESIS_C``. A ``None`` reading keeps the previous level —
    a dead sensor must not flap routing, it just stops improving it.
    """

    _ORDER = (ThermalLevel.NORMAL, ThermalLevel.WARM,
              ThermalLevel.HOT, ThermalLevel.CRITICAL)

    def __init__(self, sensor: ThermalSensor,
                 warn_c: float = WARN_C, critical_c: float = CRITICAL_C,
                 hysteresis_c: float = HYSTERESIS_C):
        if not 0 < warn_c < critical_c:
            raise ValueError("need 0 < warn_c < critical_c")
        if hysteresis_c < 0:
            raise ValueError("hysteresis_c must be >= 0")
        self._sensor = sensor
        self._warn_c = warn_c
        self._critical_c = critical_c
        self._hysteresis_c = hysteresis_c
        self._lock = threading.RLock()
        self._level = ThermalLevel.NORMAL
        self._last_temp: float | None = None

    def _entry_threshold(self, level: ThermalLevel) -> float:
        return {"warm": self._warn_c, "hot": (self._warn_c + self._critical_c) / 2,
                "critical": self._critical_c}[level.value]

    def sample(self) -> ThermalState:
        """Read the sensor and advance the level machine."""
        temp = self._sensor.read_celsius()
        with self._lock:
            if temp is not None:
                self._last_temp = temp
                idx = self._ORDER.index(self._level)
                # Step up while above entry thresholds.
                while (idx + 1 < len(self._ORDER)
                       and temp >= self._entry_threshold(self._ORDER[idx + 1])):
                    idx += 1
                # Step down while below (threshold - hysteresis).
                while (idx > 0 and temp
                       <= self._entry_threshold(self._ORDER[idx])
                       - self._hysteresis_c):
                    idx -= 1
                self._level = self._ORDER[idx]
            level = self._level
        return ThermalState(temp_c=temp, level=level,
                            derating=level.derating)

    @property
    def level(self) -> ThermalLevel:
        with self._lock:
            return self._level

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {"level": self._level.value,
                    "last_temp_c": self._last_temp,
                    "warn_c": self._warn_c,
                    "critical_c": self._critical_c,
                    "hysteresis_c": self._hysteresis_c}
