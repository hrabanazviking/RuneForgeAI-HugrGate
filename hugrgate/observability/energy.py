"""Energy metrics interface. Slice 341.

HugrGate tracks energy the way it tracks cost: as a first-class
per-decision quantity in watt-hours.  The *interface* is the point of
this slice — real joules need real power telemetry, so:

- :class:`EnergyEstimator` is the protocol: estimate Wh from a
  backend name and a latency.  Operators plug in RAPL/nvidia-smi
  readers here.
- :class:`DefaultEnergyEstimator` is a documented, auditable fallback:
  per-backend average-power coefficients (watts) times duration.  The
  coefficients are *clearly marked estimates* — see
  ``benchmarks/observability_energy_341.json`` — and the estimator
  reports which coefficients it used so nothing is mistaken for a
  measurement.
- :class:`EnergyMetrics` aggregates estimated Wh by backend and keeps
  a bounded ledger, mirroring :class:`CostMetrics
  <hugrgate.observability.cost.CostMetrics>`.

What is *not* claimed: these numbers are not meter readings.  The
artifact records the model's provenance and a determinism check
(same inputs → same outputs) instead of pretending to be hardware
truth.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Protocol

from hugrgate.errors import MetricError
from hugrgate.observability.metrics import Counter, MetricRegistry

__all__ = [
    "DEFAULT_POWER_W",
    "MAX_LEDGER",
    "DefaultEnergyEstimator",
    "EnergyEstimator",
    "EnergyMetrics",
]

#: Bound on the retained energy ledger.
MAX_LEDGER = 1000

#: Default average-power coefficients in watts, keyed by backend *class*.
#: ESTIMATES — nameplate-ish averages for capacity planning, not meter
#: readings.  ``"default"`` applies to unknown backends.  Override per
#: deployment via the constructor.
DEFAULT_POWER_W: dict[str, float] = {
    "default": 65.0,     # one busy CPU core complex, rough average
    "cpu": 65.0,
    "gpu": 250.0,        # single datacenter GPU at moderate load
    "npu": 15.0,         # edge NPU class
    "remote": 5.0,       # local NIC + amortized share only; the
                         # remote joules are someone else's meter
}


class EnergyEstimator(Protocol):
    """Estimate energy (Wh) for one backend invocation."""

    def estimate_wh(self, backend: str, latency_ms: float) -> float:
        """Return estimated watt-hours; must be finite and >= 0."""
        ...

    def describe(self) -> dict[str, Any]:
        """Provenance of the model: coefficients, source, caveats."""
        ...


class DefaultEnergyEstimator:
    """Power-coefficient model: Wh = watts * hours.

    Deterministic and auditable.  :meth:`describe` always reports the
    coefficient table in use so downstream consumers can tell an
    estimate from a measurement.
    """

    def __init__(self, power_w: dict[str, float] | None = None) -> None:
        table = dict(DEFAULT_POWER_W)
        if power_w:
            table.update(power_w)
        for name, watts in table.items():
            if not isinstance(watts, (int, float)) or watts < 0:
                raise MetricError(
                    f"power coefficient for {name!r} must be a "
                    f"non-negative number, got {watts!r}")
        self._power_w = table

    def estimate_wh(self, backend: str, latency_ms: float) -> float:
        if latency_ms < 0:
            raise MetricError(
                f"latency_ms must be >= 0, got {latency_ms!r}")
        watts = self._power_w.get(backend, self._power_w["default"])
        return watts * (latency_ms / 3_600_000.0)

    def describe(self) -> dict[str, Any]:
        return {
            "model": "power_coefficient",
            "power_w": dict(self._power_w),
            "caveat": ("Estimates from average-power coefficients, not "
                       "meter readings. Replace with hardware telemetry "
                       "for billing-grade numbers."),
        }


class EnergyMetrics:
    """Aggregate estimated energy (Wh) by backend."""

    def __init__(self, registry: MetricRegistry | None = None,
                 estimator: EnergyEstimator | None = None) -> None:
        self._registry = registry or MetricRegistry()
        self._estimator = estimator or DefaultEnergyEstimator()
        self._energy: Counter = self._registry.counter(
            "hugrgate_energy_wh_total",
            "Estimated decision energy in watt-hours by backend",
            labels=("backend",))
        self._lock = threading.Lock()
        self._ledger: deque[dict[str, Any]] = deque(maxlen=MAX_LEDGER)

    @property
    def estimator(self) -> EnergyEstimator:
        return self._estimator

    @property
    def registry(self) -> MetricRegistry:
        return self._registry

    def record(self, backend: str, latency_ms: float,
               energy_wh: float | None = None) -> float:
        """Record one invocation's energy.

        When *energy_wh* is None the estimator is used; otherwise the
        caller-supplied (e.g. metered) value is recorded.  Returns the
        recorded Wh.
        """
        if not backend:
            raise MetricError("backend name must be non-empty")
        if energy_wh is None:
            energy_wh = self._estimator.estimate_wh(backend, latency_ms)
        if not isinstance(energy_wh, (int, float)) or energy_wh != energy_wh:
            raise MetricError(
                f"energy_wh must be a finite number, got {energy_wh!r}")
        if energy_wh < 0:
            raise MetricError(
                f"energy_wh must be non-negative, got {energy_wh!r}")
        self._energy.inc(float(energy_wh), labels={"backend": backend})
        with self._lock:
            self._ledger.append({
                "timestamp": time.time(),
                "backend": backend,
                "latency_ms": latency_ms,
                "energy_wh": float(energy_wh),
            })
        return float(energy_wh)

    def total_wh(self, backend: str = "") -> float:
        total = 0.0
        for metric in self._registry.snapshot()["metrics"]:
            if metric["name"] != "hugrgate_energy_wh_total":
                continue
            for row in metric["series"]:
                if backend and row["labels"].get("backend") != backend:
                    continue
                total += row["value"]
        return total

    def summary(self) -> dict[str, Any]:
        return {
            "total_wh": round(self.total_wh(), 9),
            "estimator": self._estimator.describe(),
        }
