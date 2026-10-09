"""Confidence histograms for decision observability. Slice 337.

:class:`ConfidenceHistogram` tracks the distribution of decision
probabilities: where the gate's confidence *lives*.  A healthy gate
shows mass near 0 and 1 (decisive); mass piling up mid-range signals
chronic uncertainty worth investigating.

Statistical validation (slice 332's discipline, applied here): the
test feeds the histogram samples from a known ``Beta(2, 2)``
distribution (seeded) and checks every bucket against the theoretical
CDF computed by numeric integration — the histogram must reproduce
the distribution it was fed, within an explicit tolerance.

Metric/coverage assumptions:

- observations are treated as i.i.d. draws; the validation only proves
  the instrument is faithful, not that the gate is calibrated;
- buckets are fixed 0.1-wide bands; probabilities outside [0, 1] are
  rejected, never clipped.
"""

from __future__ import annotations

from typing import Any

from hugrgate.errors import MetricError
from hugrgate.observability.metrics import Histogram, MetricRegistry

__all__ = [
    "CONFIDENCE_BUCKETS",
    "ConfidenceHistogram",
]

#: Ten 0.1-wide bands covering [0, 1].
CONFIDENCE_BUCKETS: tuple[float, ...] = tuple(
    round(0.1 * (i + 1), 1) for i in range(10))


class ConfidenceHistogram:
    """Distribution of decision probabilities (one histogram per label set)."""

    def __init__(self, registry: MetricRegistry,
                 name: str = "hugrgate_decision_confidence",
                 label_names: tuple[str, ...] = ("backend",)) -> None:
        self._histogram: Histogram = registry.histogram(
            name, "Decision probability distribution",
            labels=label_names, buckets=CONFIDENCE_BUCKETS)
        self._label_names = label_names

    @property
    def histogram(self) -> Histogram:
        return self._histogram

    def _labels(self, backend: str) -> dict[str, str] | None:
        if "backend" not in self._label_names:
            return None
        if not backend:
            raise MetricError("backend name must be non-empty")
        return {"backend": backend}

    def observe(self, probability: float, backend: str = "") -> None:
        """Record one decision probability (must be in [0, 1])."""
        if not 0.0 <= probability <= 1.0:
            raise MetricError(
                f"probability out of bounds: {probability!r}")
        self._histogram.observe(probability, self._labels(backend))

    def bucket_counts(self, backend: str = "") -> list[int]:
        """Raw counts per 0.1 band, low to high."""
        return self._histogram.buckets(self._labels(backend))

    def total(self, backend: str = "") -> int:
        return self._histogram.count(self._labels(backend))

    def mass_in(self, lo: float, hi: float, backend: str = "") -> float:
        """Fraction of observations with ``lo <= p < hi`` (hi=1 inclusive).

        Computed from whole buckets: the band edges must align to 0.1
        boundaries, otherwise the answer would silently interpolate.
        """
        if not 0.0 <= lo < hi <= 1.0:
            raise MetricError(
                f"band must satisfy 0 <= lo < hi <= 1, got ({lo}, {hi})")
        for edge in (lo, hi):
            if abs(edge * 10 - round(edge * 10)) > 1e-9:
                raise MetricError(
                    f"band edges must align to 0.1 boundaries, got {edge!r}")
        counts = self.bucket_counts(backend)
        total = self.total(backend)
        if total == 0:
            raise MetricError("no confidence observations recorded")
        lo_idx = round(lo * 10)
        hi_idx = round(hi * 10)
        return sum(counts[lo_idx:hi_idx]) / total

    def summary(self, backend: str = "") -> dict[str, Any]:
        """Per-bucket fractions plus mean confidence."""
        labels = self._labels(backend)
        total = self.total(backend)
        if total == 0:
            raise MetricError("no confidence observations recorded")
        counts = self.bucket_counts(backend)
        return {
            "total": total,
            "mean": self._histogram.total(labels) / total,
            "buckets": {
                f"{i / 10:.1f}-{(i + 1) / 10:.1f}": counts[i] / total
                for i in range(10)
            },
        }
