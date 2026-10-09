"""Energy-quality objective. Slice 134.

Local inference is not free: every millisecond of GPU/CPU time burns
watt-hours. :class:`EnergyQualityObjective` scalarizes

    score = quality_weight * quality - energy_weight * (energy_wh / energy_scale)

and :func:`estimate_energy_wh` turns a latency measurement into a
watt-hour estimate from a host power model, so energy claims rest on
measured latency rather than vibes:

    energy_wh = watts * latency_s / 3600

The default power draws are conservative, documented estimates for
typical hardware classes — callers with real power telemetry should
pass their own ``watts``. Like slice 133, this module ships
:func:`measure_energy`, which pairs :func:`measure_latency` with the
power model to produce a reproducible energy artifact.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hugrgate.adaptive.cost_quality import (
    RouteObjective,
    RoutingCandidate,
)
from hugrgate.adaptive.latency_quality import (
    LatencyMeasurement,
    measure_latency,
)
from hugrgate.errors import SpecError

__all__ = [
    "DEFAULT_LOCAL_WATTS",
    "DEFAULT_REMOTE_WATTS",
    "EnergyMeasurement",
    "EnergyQualityObjective",
    "estimate_energy_wh",
    "measure_energy",
]

#: Conservative power draw for on-device inference (mid-range GPU/CPU).
DEFAULT_LOCAL_WATTS = 150.0
#: Power attributed to the client side of a remote call (NIC + idle host).
#: The datacenter side is the provider's bill, not ours — this is the
#: local cost of going remote.
DEFAULT_REMOTE_WATTS = 25.0


def estimate_energy_wh(latency_ms: float, watts: float) -> float:
    """Watt-hours for ``latency_ms`` at ``watts`` average draw."""
    if latency_ms < 0:
        raise SpecError(f"latency_ms must be >= 0, got {latency_ms}")
    if watts <= 0:
        raise SpecError(f"watts must be > 0, got {watts}")
    return watts * (latency_ms / 1000.0) / 3600.0


@dataclass(frozen=True)
class EnergyMeasurement:
    """Reproducible energy artifact: measured latency x power model."""

    latency: LatencyMeasurement
    watts: float
    mean_wh: float
    p95_wh: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "latency": self.latency.to_dict(),
            "watts": self.watts,
            "mean_wh": self.mean_wh,
            "p95_wh": self.p95_wh,
        }


def measure_energy(fn: Callable[[], Any], watts: float,
                   n_runs: int = 50, label: str = "") -> EnergyMeasurement:
    """Measure ``fn``'s latency distribution and convert to watt-hours."""
    latency = measure_latency(fn, n_runs=n_runs, label=label)
    return EnergyMeasurement(
        latency=latency,
        watts=watts,
        mean_wh=estimate_energy_wh(latency.mean_ms, watts),
        p95_wh=estimate_energy_wh(latency.p95_ms, watts),
    )


class EnergyQualityObjective(RouteObjective):
    """Trade expected quality against energy consumption."""

    name = "energy_quality"

    def __init__(self, *, quality_weight: float = 1.0,
                 energy_weight: float = 1.0,
                 energy_scale: float = 0.01) -> None:
        if quality_weight < 0 or energy_weight < 0:
            raise SpecError(
                "objective weights must be non-negative, got "
                f"quality_weight={quality_weight}, "
                f"energy_weight={energy_weight}")
        if quality_weight == 0 and energy_weight == 0:
            raise SpecError(
                "at least one of quality_weight/energy_weight must be "
                "positive")
        if energy_scale <= 0:
            raise SpecError(f"energy_scale must be > 0, got {energy_scale}")
        self.quality_weight = quality_weight
        self.energy_weight = energy_weight
        self.energy_scale = energy_scale

    def score(self, candidate: RoutingCandidate) -> float:
        return (self.quality_weight * candidate.quality
                - self.energy_weight
                * (candidate.energy_wh / self.energy_scale))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "quality_weight": self.quality_weight,
            "energy_weight": self.energy_weight,
            "energy_scale": self.energy_scale,
        }
