"""Metric primitives for HugrGate observability. Slice 326.

Campaign VI's :mod:`hugrgate.adaptive.telemetry` keeps an *event log* for
offline learning; this module is the complementary *live* instrument
surface: :class:`Counter`, :class:`Gauge`, and :class:`Histogram`
instruments registered in a :class:`MetricRegistry`.

Design rules (Yrsa Execution Law 14 — bounded, typed, auditable):

- metric and label names must match Prometheus naming rules; violations
  raise :class:`~hugrgate.errors.MetricError` at registration, never
  silently;
- label sets are fixed per metric; a wrong label set raises;
- label cardinality is bounded by ``max_series``: when the cap is hit,
  *new* label combinations raise instead of growing memory without
  bound;
- counters never decrease; observations must be finite;
- every instrument is thread-safe (one re-entrant lock per registry);
- :meth:`MetricRegistry.snapshot` returns a JSON-serializable dict so
  exporters (Prometheus text in slice 334, dashboards in slice 335)
  never touch instrument internals.
"""

from __future__ import annotations

import math
import re
import threading
import time
from bisect import bisect_left
from typing import Any

from hugrgate.errors import MetricError

__all__ = [
    "DEFAULT_LATENCY_BUCKETS",
    "Counter",
    "Gauge",
    "Histogram",
    "MetricRegistry",
    "validate_metric_name",
]

#: Default histogram buckets for latencies, in seconds.  Powers chosen so
#: a 1 ms decision and a 10 s timeout both land inside the range.
DEFAULT_LATENCY_BUCKETS: tuple[float, ...] = (
    0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5,
    5.0, 10.0,
)

_NAME_RE = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")


def validate_metric_name(name: str) -> str:
    """Validate a metric or label name; return it unchanged or raise."""
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise MetricError(
            f"invalid metric name {name!r}: must match {_NAME_RE.pattern}")
    return name


def _series_key(labels: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(labels.items()))


class _BaseMetric:
    """Shared registration/validation for the three instrument kinds."""

    _kind = "unknown"

    def __init__(self, name: str, description: str,
                 label_names: tuple[str, ...], registry: MetricRegistry) -> None:
        validate_metric_name(name)
        for label in label_names:
            validate_metric_name(label)
        if len(set(label_names)) != len(label_names):
            raise MetricError(f"metric {name!r}: duplicate label names")
        self._name = name
        self._description = description
        self._label_names = label_names
        self._registry = registry
        self._lock = registry._lock
        self._series: dict[tuple[tuple[str, str], ...], Any] = {}

    @property
    def name(self) -> str:
        return self._name

    @property
    def kind(self) -> str:
        return self._kind

    def _slot(self, labels: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
        given = dict(labels or {})
        if set(given) != set(self._label_names):
            raise MetricError(
                f"metric {self._name!r}: expected labels "
                f"{sorted(self._label_names)}, got {sorted(given)}")
        for label_key, label_value in given.items():
            if not isinstance(label_value, str):
                raise MetricError(
                    f"metric {self._name!r}: label {label_key!r} value must "
                    f"be a string, got {type(label_value).__name__}")
        series_key = _series_key(given)
        with self._lock:
            if series_key not in self._series:
                self._registry._check_cardinality(self._name)
                self._series[series_key] = self._new_series()
                self._registry._series_total += 1
        return series_key

    def _new_series(self) -> Any:  # pragma: no cover - overridden
        raise NotImplementedError


class Counter(_BaseMetric):
    """A monotonically increasing counter."""

    _kind = "counter"

    def _new_series(self) -> list[float]:
        return [0.0]

    def inc(self, amount: float = 1.0,
            labels: dict[str, str] | None = None) -> None:
        """Increment by *amount* (must be non-negative and finite)."""
        if not math.isfinite(amount) or amount < 0:
            raise MetricError(
                f"counter {self._name!r}: increment must be finite and "
                f"non-negative, got {amount!r}")
        key = self._slot(labels)
        with self._lock:
            self._series[key][0] += amount

    def value(self, labels: dict[str, str] | None = None) -> float:
        key = self._slot(labels)
        with self._lock:
            return self._series[key][0]


class Gauge(_BaseMetric):
    """A gauge: an instantaneous value that may move either way."""

    _kind = "gauge"

    def _new_series(self) -> list[float]:
        return [0.0]

    def set(self, value: float, labels: dict[str, str] | None = None) -> None:
        if not math.isfinite(value):
            raise MetricError(
                f"gauge {self._name!r}: value must be finite, got {value!r}")
        key = self._slot(labels)
        with self._lock:
            self._series[key][0] = value

    def inc(self, amount: float = 1.0,
            labels: dict[str, str] | None = None) -> None:
        if not math.isfinite(amount):
            raise MetricError(
                f"gauge {self._name!r}: increment must be finite")
        key = self._slot(labels)
        with self._lock:
            self._series[key][0] += amount

    def dec(self, amount: float = 1.0,
            labels: dict[str, str] | None = None) -> None:
        self.inc(-amount, labels)

    def value(self, labels: dict[str, str] | None = None) -> float:
        key = self._slot(labels)
        with self._lock:
            return self._series[key][0]


class Histogram(_BaseMetric):
    """An explicit-bucket histogram with sum and count."""

    _kind = "histogram"

    def __init__(self, name: str, description: str,
                 label_names: tuple[str, ...], registry: MetricRegistry,
                 buckets: tuple[float, ...] = DEFAULT_LATENCY_BUCKETS) -> None:
        if not buckets:
            raise MetricError(f"histogram {name!r}: needs at least one bucket")
        if any(not math.isfinite(b) or b <= 0 for b in buckets):
            raise MetricError(
                f"histogram {name!r}: buckets must be finite and positive")
        if list(buckets) != sorted(buckets):
            raise MetricError(
                f"histogram {name!r}: buckets must be ascending")
        if len(set(buckets)) != len(buckets):
            raise MetricError(f"histogram {name!r}: duplicate buckets")
        self._buckets = tuple(buckets)
        super().__init__(name, description, label_names, registry)

    def _new_series(self) -> list[Any]:
        return [[0] * len(self._buckets), 0.0, 0]  # counts, sum, count

    def observe(self, value: float,
                labels: dict[str, str] | None = None) -> None:
        """Record one observation (must be finite and non-negative)."""
        if not math.isfinite(value) or value < 0:
            raise MetricError(
                f"histogram {self._name!r}: observation must be finite and "
                f"non-negative, got {value!r}")
        key = self._slot(labels)
        with self._lock:
            counts, total, count = self._series[key]
            idx = bisect_left(self._buckets, value)
            if idx < len(self._buckets):
                counts[idx] += 1
            # values above the last bucket are counted in ``count`` and
            # ``sum`` but in no bucket — Prometheus renders an implicit
            # +Inf bucket for them (slice 334).
            self._series[key][1] = total + value
            self._series[key][2] = count + 1

    def buckets(self, labels: dict[str, str] | None = None) -> list[int]:
        key = self._slot(labels)
        with self._lock:
            return list(self._series[key][0])

    def count(self, labels: dict[str, str] | None = None) -> int:
        key = self._slot(labels)
        with self._lock:
            return self._series[key][2]

    def total(self, labels: dict[str, str] | None = None) -> float:
        key = self._slot(labels)
        with self._lock:
            return self._series[key][1]

    def percentile(self, q: float,
                   labels: dict[str, str] | None = None) -> float:
        """Estimate the q-th percentile by linear interpolation *within*
        the bucket that holds the target rank.

        Bounded and auditable: the estimate always lies inside a real
        bucket, and slice 336 validates it against exact percentiles on
        controlled data.
        """
        if not 0.0 <= q <= 1.0:
            raise MetricError(
                f"histogram {self._name!r}: percentile q must be in "
                f"[0, 1], got {q!r}")
        key = self._slot(labels)
        with self._lock:
            counts = list(self._series[key][0])
        total = sum(counts)
        if total == 0:
            raise MetricError(
                f"histogram {self._name!r}: no observations recorded")
        rank = q * total
        cumulative = 0
        for idx, bucket_count in enumerate(counts):
            cumulative += bucket_count
            if (cumulative >= rank and rank > 0) or (rank == 0 and idx == 0):
                lower = self._buckets[idx - 1] if idx > 0 else 0.0
                upper = self._buckets[idx]
                if bucket_count == 0:
                    return lower
                # fraction of the way through this bucket's mass
                before = cumulative - bucket_count
                frac = (rank - before) / bucket_count
                return lower + frac * (upper - lower)
        return self._buckets[-1]


class MetricRegistry:
    """Owns every instrument; the single choke point for cardinality.

    ``max_series`` bounds the total number of distinct label
    combinations across *all* metrics in the registry.  Crossing it
    raises :class:`~hugrgate.errors.MetricError` on the offending
    recording instead of growing memory without bound.
    """

    def __init__(self, max_series: int = 1000) -> None:
        if not isinstance(max_series, int) or max_series < 1:
            raise MetricError("max_series must be a positive integer")
        self._max_series = max_series
        self._lock = threading.RLock()
        self._metrics: dict[str, _BaseMetric] = {}
        self._series_total = 0

    def _check_cardinality(self, name: str) -> None:
        if self._series_total >= self._max_series:
            raise MetricError(
                f"metric {name!r}: label cardinality cap "
                f"({self._max_series} series) reached — refusing new series")

    def _register(self, metric: _BaseMetric) -> _BaseMetric:
        with self._lock:
            if metric.name in self._metrics:
                existing = self._metrics[metric.name]
                if (type(existing) is not type(metric)
                        or existing._label_names != metric._label_names):
                    raise MetricError(
                        f"metric {metric.name!r}: conflicting re-registration "
                        f"(kind {existing.kind} labels "
                        f"{sorted(existing._label_names)})")
                return existing
            self._metrics[metric.name] = metric
            return metric

    def counter(self, name: str, description: str = "",
                labels: tuple[str, ...] = ()) -> Counter:
        return self._register(Counter(name, description, labels, self))  # type: ignore[return-value]

    def gauge(self, name: str, description: str = "",
              labels: tuple[str, ...] = ()) -> Gauge:
        return self._register(Gauge(name, description, labels, self))  # type: ignore[return-value]

    def histogram(self, name: str, description: str = "",
                  labels: tuple[str, ...] = (),
                  buckets: tuple[float, ...] = DEFAULT_LATENCY_BUCKETS
                  ) -> Histogram:
        return self._register(Histogram(name, description, labels, self, buckets))  # type: ignore[return-value]

    def get(self, name: str) -> _BaseMetric | None:
        with self._lock:
            return self._metrics.get(name)

    def timer(self, histogram: Histogram,
              labels: dict[str, str] | None = None) -> _Timer:
        """Return a context manager that observes elapsed seconds."""
        return _Timer(histogram, labels)

    def snapshot(self) -> dict[str, Any]:
        """JSON-serializable view of every series, for exporters."""
        out: dict[str, Any] = {"generated_at": time.time(), "metrics": []}
        with self._lock:
            for metric in self._metrics.values():
                entry: dict[str, Any] = {
                    "name": metric.name,
                    "kind": metric.kind,
                    "description": metric._description,
                    "series": [],
                }
                for key, series in metric._series.items():
                    row: dict[str, Any] = {"labels": dict(key)}
                    if isinstance(metric, Histogram):
                        counts, total, count = series
                        row["buckets"] = {
                            str(b): c for b, c in zip(metric._buckets, counts,
                                                     strict=True)}
                        row["sum"] = total
                        row["count"] = count
                    else:
                        row["value"] = series[0]
                    entry["series"].append(row)
                out["metrics"].append(entry)
        return out


class _Timer:
    """Context manager: observe wall-clock seconds into a histogram."""

    def __init__(self, histogram: Histogram,
                 labels: dict[str, str] | None) -> None:
        self._histogram = histogram
        self._labels = labels
        self._start = 0.0

    def __enter__(self) -> _Timer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._histogram.observe(time.perf_counter() - self._start,
                                self._labels)
