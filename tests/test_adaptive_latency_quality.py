"""Slice 133 — latency-quality objective tests."""

from __future__ import annotations

import time

import pytest

from hugrgate.adaptive.cost_quality import RoutingCandidate
from hugrgate.adaptive.latency_quality import (
    LatencyMeasurement,
    LatencyQualityObjective,
    compare_to_baseline,
    measure_latency,
)
from hugrgate.errors import SpecError


def cand(name="a", quality=0.8, latency_ms=100.0):
    return RoutingCandidate(name=name, quality=quality, cost=0.0,
                            latency_ms=latency_ms, energy_wh=0.0)


# --- success ---------------------------------------------------------------

def test_faster_wins_at_equal_quality():
    obj = LatencyQualityObjective(latency_scale=1000.0)
    fast, slow = cand("fast", latency_ms=50.0), cand("slow", latency_ms=900.0)
    assert obj.score(fast) > obj.score(slow)
    assert obj.rank([slow, fast])[0].name == "fast"

def test_quality_can_outweigh_latency():
    obj = LatencyQualityObjective(quality_weight=5.0, latency_weight=1.0,
                                  latency_scale=1000.0)
    # quality edge 0.4*5=2.0 vs latency penalty (900-50)/1000=0.85
    great = cand("great", quality=0.9, latency_ms=900.0)
    meh = cand("meh", quality=0.5, latency_ms=50.0)
    assert obj.score(great) > obj.score(meh)

def test_measure_latency_produces_real_artifact():
    def work():
        time.sleep(0.001)
    m = measure_latency(work, n_runs=10, label="sleep-1ms")
    assert isinstance(m, LatencyMeasurement)
    assert m.n_runs == 10 and m.label == "sleep-1ms"
    assert 0 < m.min_ms <= m.p50_ms <= m.p95_ms <= m.max_ms
    assert m.mean_ms >= 0.5  # really slept ~1ms; never invented

def test_compare_to_baseline_computes_deltas():
    m = LatencyMeasurement(n_runs=10, mean_ms=80.0, p50_ms=75.0,
                           p95_ms=120.0, min_ms=60.0, max_ms=130.0,
                           label="candidate")
    report = compare_to_baseline(m, 100.0, baseline_label="prod")
    assert report["delta_ms"] == pytest.approx(-20.0)
    assert report["ratio"] == pytest.approx(0.8)
    assert report["faster_than_baseline"] is True
    assert report["baseline_label"] == "prod"
    assert report["measured_p95_ms"] == 120.0

def test_slower_than_baseline_flag():
    m = LatencyMeasurement(n_runs=5, mean_ms=150.0, p50_ms=150.0,
                           p95_ms=150.0, min_ms=150.0, max_ms=150.0)
    report = compare_to_baseline(m, 100.0)
    assert report["faster_than_baseline"] is False
    assert report["delta_ms"] == pytest.approx(50.0)

# --- failure ---------------------------------------------------------------

def test_bad_weights_rejected():
    with pytest.raises(SpecError):
        LatencyQualityObjective(latency_weight=-1.0)
    with pytest.raises(SpecError):
        LatencyQualityObjective(quality_weight=0.0, latency_weight=0.0)
    with pytest.raises(SpecError):
        LatencyQualityObjective(latency_scale=0.0)

def test_measure_latency_needs_runs():
    with pytest.raises(SpecError):
        measure_latency(lambda: None, n_runs=0)

def test_baseline_must_be_positive():
    m = LatencyMeasurement(n_runs=1, mean_ms=1.0, p50_ms=1.0, p95_ms=1.0,
                           min_ms=1.0, max_ms=1.0)
    with pytest.raises(SpecError):
        compare_to_baseline(m, 0.0)
