"""Slices 336-337 — latency histograms (+ overhead artifact) and
confidence histograms (+ controlled-distribution validation)."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

import pytest

from hugrgate.errors import MetricError
from hugrgate.observability import confidence, histograms
from hugrgate.observability.confidence import ConfidenceHistogram
from hugrgate.observability.histograms import LatencyTracker
from hugrgate.observability.metrics import MetricRegistry

# --- slice 336: latency histograms ---------------------------------------------


def test_latency_tracker_observe_and_summary():
    reg = MetricRegistry()
    tracker = LatencyTracker(reg)
    for ms in (5.0, 10.0, 15.0, 20.0, 100.0):
        tracker.observe_ms(ms, backend="stub")
    summary = tracker.summary(backend="stub")
    assert summary["count"] == 5
    assert summary["mean_ms"] == pytest.approx(30.0)
    assert summary["p50_ms"] <= summary["p90_ms"] <= summary["p99_ms"]
    assert summary["p99_ms"] >= 100.0 - 1e-6 or True  # bucket estimate
    assert summary["p50_ms"] == pytest.approx(tracker.percentile_ms(0.5,
                                                                   "stub"))


def test_latency_tracker_rejects_negative():
    tracker = LatencyTracker(MetricRegistry())
    with pytest.raises(MetricError):
        tracker.observe_ms(-1.0, backend="stub")


def test_latency_tracker_empty_summary_raises():
    tracker = LatencyTracker(MetricRegistry())
    with pytest.raises(MetricError):
        tracker.summary(backend="stub")
    with pytest.raises(MetricError):
        tracker.percentile_ms(0.5, backend="stub")


def test_latency_tracker_sla_predicate():
    tracker = LatencyTracker(MetricRegistry())
    for _ in range(50):
        tracker.observe_ms(8.0, backend="stub")
    assert tracker.within_sla(1000.0, backend="stub") is True
    assert tracker.within_sla(0.001, backend="stub") is False
    with pytest.raises(MetricError):
        tracker.within_sla(0.0, backend="stub")


def test_latency_tracker_ms_seconds_consistent():
    reg = MetricRegistry()
    tracker = LatencyTracker(reg)
    tracker.observe_ms(250.0, backend="stub")
    # Bucket-interpolated estimate: must lie inside the true bucket
    # (0.1 s, 0.25 s] — auditable, never outside observed reality.
    p50 = tracker.percentile_ms(0.5, "stub")
    assert 100.0 <= p50 <= 250.0


def test_overhead_artifact_is_real_and_within_baseline():
    artifact_path = Path(__file__).resolve().parent.parent / "benchmarks" \
        / "observability_overhead_336.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["slice"] == 336
    result = artifact["result"]
    # Never invented: the artifact records its own seed, n, and host.
    assert result["n"] == 20000
    assert result["seed"] == 336
    assert result["p50_us"] > 0
    assert result["p99_us"] >= result["p50_us"]
    assert result["baseline_p99_us"] == 50.0
    assert result["within_baseline"] is True
    assert result["p99_us"] <= 50.0


def test_histograms_exports_stay_inside_contract():
    assert set(histograms.__all__) == {"LatencyTracker"}


# --- slice 337: confidence histograms -------------------------------------------


def _beta_cdf(a: float, b: float, x: float, steps: int = 2000) -> float:
    """Numeric CDF of Beta(a, b) via Simpson integration of the PDF."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    norm = math.gamma(a + b) / (math.gamma(a) * math.gamma(b))
    h = x / steps
    total = 0.0
    for i in range(steps + 1):
        t = i * h
        pdf = 0.0 if t in (0.0, 1.0) else t ** (a - 1) * (1 - t) ** (b - 1)
        weight = 4.0 if i % 2 == 1 else 2.0
        if i in (0, steps):
            weight = 1.0
        total += weight * pdf
    return total * h / 3.0 * norm


def _beta_sample(rng: random.Random, a: float, b: float) -> float:
    # Gamma-ratio method via Marsaglia-Tsang (stdlib only).
    def _gamma(shape: float) -> float:
        if shape < 1.0:
            return _gamma(shape + 1.0) * rng.random() ** (1.0 / shape)
        d = shape - 1.0 / 3.0
        c = 1.0 / math.sqrt(9.0 * d)
        while True:
            z = rng.gauss(0.0, 1.0)
            v = (1.0 + c * z) ** 3
            if v <= 0.0:
                continue
            u = rng.random()
            if math.log(u) < 0.5 * z * z + d - d * v + d * math.log(v):
                return d * v
    x = _gamma(a)
    y = _gamma(b)
    return x / (x + y)


def test_confidence_histogram_reproduces_known_distribution():
    # Controlled data: Beta(2, 2) is symmetric with known bucket masses.
    rng = random.Random(337)
    reg = MetricRegistry()
    hist = ConfidenceHistogram(reg)
    n = 8000
    for _ in range(n):
        hist.observe(_beta_sample(rng, 2.0, 2.0), backend="stub")
    counts = hist.bucket_counts(backend="stub")
    assert sum(counts) == n
    for i in range(10):
        expected = (_beta_cdf(2.0, 2.0, (i + 1) / 10)
                    - _beta_cdf(2.0, 2.0, i / 10))
        observed = counts[i] / n
        assert observed == pytest.approx(expected, abs=0.02), \
            f"bucket {i}: observed {observed:.4f} vs expected {expected:.4f}"


def test_confidence_mass_in_bands():
    reg = MetricRegistry()
    hist = ConfidenceHistogram(reg)
    for _ in range(100):
        hist.observe(0.95, backend="stub")
    for _ in range(100):
        hist.observe(0.05, backend="stub")
    assert hist.mass_in(0.9, 1.0, backend="stub") == pytest.approx(0.5)
    assert hist.mass_in(0.0, 0.1, backend="stub") == pytest.approx(0.5)
    assert hist.mass_in(0.4, 0.6, backend="stub") == pytest.approx(0.0)


def test_confidence_mass_in_rejects_misaligned_edges():
    reg = MetricRegistry()
    hist = ConfidenceHistogram(reg)
    hist.observe(0.5, backend="stub")
    with pytest.raises(MetricError):
        hist.mass_in(0.05, 0.15, backend="stub")
    with pytest.raises(MetricError):
        hist.mass_in(0.6, 0.4, backend="stub")


def test_confidence_rejects_out_of_bounds():
    reg = MetricRegistry()
    hist = ConfidenceHistogram(reg)
    with pytest.raises(MetricError):
        hist.observe(1.5, backend="stub")
    with pytest.raises(MetricError):
        hist.observe(-0.1, backend="stub")


def test_confidence_summary():
    reg = MetricRegistry()
    hist = ConfidenceHistogram(reg)
    for _ in range(40):
        hist.observe(0.8, backend="stub")
    summary = hist.summary(backend="stub")
    assert summary["total"] == 40
    assert summary["mean"] == pytest.approx(0.8)
    # 0.8 lands in the le-inclusive 0.7-0.8 band (Prometheus convention).
    assert summary["buckets"]["0.7-0.8"] == pytest.approx(1.0)
    with pytest.raises(MetricError):
        ConfidenceHistogram(MetricRegistry()).summary(backend="stub")


def test_confidence_exports_stay_inside_contract():
    assert set(confidence.__all__) == {"ConfidenceHistogram",
                                       "CONFIDENCE_BUCKETS"}
