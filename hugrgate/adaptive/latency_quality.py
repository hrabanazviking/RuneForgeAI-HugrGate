"""Latency-quality objective. Slice 133.

Same scalarization shape as slice 132, with wall-clock latency as the
price of quality:

    score = quality_weight * quality - latency_weight * (latency_ms / latency_scale)

Plus the slice's required measurement discipline:
:func:`measure_latency` runs a callable ``n_runs`` times and returns a
:class:`LatencyMeasurement` (mean/p50/p95/min/max — computed, never
invented), and :func:`compare_to_baseline` turns a measurement and an
explicit baseline number into a delta/ratio report. The benchmark in
slice 149 reuses these so every latency claim in Campaign VI is backed
by a reproducible artifact.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict

from hugrgate.errors import SpecError

from hugrgate.adaptive.cost_quality import (
    RouteObjective,
    RoutingCandidate,
)

__all__ = [
    "LatencyMeasurement",
    "LatencyQualityObjective",
    "measure_latency",
    "compare_to_baseline",
]


@dataclass(frozen=True)
class LatencyMeasurement:
    """Reproducible latency artifact: measured, not asserted."""

    n_runs: int
    mean_ms: float
    p50_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float
    label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_runs": self.n_runs,
            "mean_ms": self.mean_ms,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "min_ms": self.min_ms,
            "max_ms": self.max_ms,
            "label": self.label,
        }


def _percentile(sorted_values: list, pct: float) -> float:
    if not sorted_values:
        raise SpecError("cannot take a percentile of no samples")
    idx = min(int(pct / 100.0 * len(sorted_values)),
              len(sorted_values) - 1)
    return sorted_values[idx]


def measure_latency(fn: Callable[[], Any], n_runs: int = 50,
                    label: str = "") -> LatencyMeasurement:
    """Time ``fn`` ``n_runs`` times; return the measured distribution."""
    if n_runs < 1:
        raise SpecError(f"n_runs must be >= 1, got {n_runs}")
    samples = []
    for _ in range(n_runs):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    ordered = sorted(samples)
    return LatencyMeasurement(
        n_runs=n_runs,
        mean_ms=statistics.fmean(samples),
        p50_ms=_percentile(ordered, 50.0),
        p95_ms=_percentile(ordered, 95.0),
        min_ms=ordered[0],
        max_ms=ordered[-1],
        label=label,
    )


def compare_to_baseline(measurement: LatencyMeasurement,
                        baseline_mean_ms: float,
                        baseline_label: str = "baseline") -> Dict[str, Any]:
    """Compare a measurement against an explicit baseline number.

    Returns deltas and ratios computed from the two inputs — both must
    be real measurements, never placeholders.
    """
    if baseline_mean_ms <= 0:
        raise SpecError(
            f"baseline_mean_ms must be > 0, got {baseline_mean_ms}")
    mean = measurement.mean_ms
    return {
        "label": measurement.label,
        "baseline_label": baseline_label,
        "n_runs": measurement.n_runs,
        "measured_mean_ms": mean,
        "measured_p95_ms": measurement.p95_ms,
        "baseline_mean_ms": baseline_mean_ms,
        "delta_ms": mean - baseline_mean_ms,
        "ratio": mean / baseline_mean_ms,
        "faster_than_baseline": mean < baseline_mean_ms,
    }


class LatencyQualityObjective(RouteObjective):
    """Trade expected quality against wall-clock latency."""

    name = "latency_quality"

    def __init__(self, *, quality_weight: float = 1.0,
                 latency_weight: float = 1.0,
                 latency_scale: float = 1000.0) -> None:
        if quality_weight < 0 or latency_weight < 0:
            raise SpecError(
                "objective weights must be non-negative, got "
                f"quality_weight={quality_weight}, "
                f"latency_weight={latency_weight}")
        if quality_weight == 0 and latency_weight == 0:
            raise SpecError(
                "at least one of quality_weight/latency_weight must be "
                "positive")
        if latency_scale <= 0:
            raise SpecError(
                f"latency_scale must be > 0, got {latency_scale}")
        self.quality_weight = quality_weight
        self.latency_weight = latency_weight
        self.latency_scale = latency_scale

    def score(self, candidate: RoutingCandidate) -> float:
        return (self.quality_weight * candidate.quality
                - self.latency_weight
                * (candidate.latency_ms / self.latency_scale))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "quality_weight": self.quality_weight,
            "latency_weight": self.latency_weight,
            "latency_scale": self.latency_scale,
        }
