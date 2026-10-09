"""Slice 364 — Latency-aware evaluation.

Covers: SLO compliance math, budgeted accuracy (in-SLO only),
percentile/tail reporting, fastest/best_budgeted_accuracy/meets_slo
queries, SLO validation, empty input, unknown backend, and
serialization round-trip.  Uses small real sleeps via StubBackend
delays — wall-clock assertions use generous bounds.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionSpec
from hugrgate.errors import EvalError
from hugrgate.evlab import (
    LatencyReport,
    latency_aware_evaluate,
)


def _dataset(n=10):
    return {
        "name": "lat-smoke",
        "version": "1.0.0",
        "spec": DecisionSpec(type="categorical",
                             options=["a", "b"]).to_dict(),
        "items": [{"state": {"x": i}, "expected": "a"} for i in range(n)],
    }


def _gate_with_delays(gate_with_stub):
    from tests.conftest import StubBackend
    gate_with_stub.register(StubBackend(name="fast", value="a"))
    gate_with_stub.register(StubBackend(name="slow", value="a",
                                        delay=0.05))
    return gate_with_stub


def test_compliance_and_percentiles(gate_with_stub):
    gate = _gate_with_delays(gate_with_stub)
    report = latency_aware_evaluate(_dataset(), gate, ["fast", "slow"],
                                    slo_ms=20.0)
    fast, slow = report.backends["fast"], report.backends["slow"]
    assert fast["slo_compliance"] == pytest.approx(1.0)
    assert slow["slo_compliance"] == pytest.approx(0.0)
    assert slow["latency_p50_ms"] >= 40.0  # 50ms sleep, generous bound
    assert fast["latency_p50_ms"] < 20.0
    assert slow["latency_p99_ms"] >= slow["latency_p50_ms"]
    assert fast["tail_heaviness"] is not None


def test_budgeted_accuracy(gate_with_stub):
    gate = _gate_with_delays(gate_with_stub)
    report = latency_aware_evaluate(_dataset(), gate, ["fast", "slow"],
                                    slo_ms=20.0)
    # fast: accurate and in-SLO; slow: accurate but never in-SLO.
    assert report.backends["fast"]["budgeted_accuracy"] == \
        pytest.approx(1.0)
    assert report.backends["slow"]["budgeted_accuracy"] is None
    assert report.backends["slow"]["budgeted_n"] == 0
    name, acc = report.best_budgeted_accuracy()
    assert name == "fast"
    assert acc == pytest.approx(1.0)


def test_meets_slo(gate_with_stub):
    gate = _gate_with_delays(gate_with_stub)
    report = latency_aware_evaluate(_dataset(), gate, ["fast", "slow"],
                                    slo_ms=20.0)
    assert report.meets_slo("fast") is True
    assert report.meets_slo("slow") is False
    assert report.meets_slo("fast", min_compliance=0.5) is True
    with pytest.raises(EvalError):
        report.meets_slo("fast", min_compliance=1.5)
    with pytest.raises(EvalError):
        report.meets_slo("ghost")


def test_fastest(gate_with_stub):
    gate = _gate_with_delays(gate_with_stub)
    report = latency_aware_evaluate(_dataset(), gate, ["fast", "slow"],
                                    slo_ms=20.0)
    assert report.fastest() == "fast"


def test_slo_validation(gate_with_stub):
    with pytest.raises(EvalError):
        latency_aware_evaluate(_dataset(), gate_with_stub, ["stub"],
                               slo_ms=0.0)
    with pytest.raises(EvalError):
        latency_aware_evaluate(_dataset(), gate_with_stub, ["stub"],
                               slo_ms=-5.0)


def test_empty_items_rejected(gate_with_stub):
    ds = _dataset(5)
    ds["items"] = []
    with pytest.raises(EvalError):
        latency_aware_evaluate(ds, gate_with_stub, ["stub"])


def test_no_backends_rejected(gate_with_stub):
    from hugrgate import DecisionSpec as DS
    ds = _dataset(5)
    # stub only supports categorical: nothing can serve this spec.
    ds["spec"] = DS(type="numeric", minimum=0.0,
                    maximum=1.0).to_dict()
    with pytest.raises(EvalError):
        latency_aware_evaluate(ds, gate_with_stub)


def test_report_roundtrip(gate_with_stub):
    report = latency_aware_evaluate(_dataset(), gate_with_stub, ["stub"],
                                    slo_ms=50.0)
    clone = LatencyReport.from_dict(report.to_dict())
    assert clone.to_dict() == report.to_dict()
    assert clone.fastest() == "stub"
    assert clone.meets_slo("stub") is True


def test_max_items(gate_with_stub):
    report = latency_aware_evaluate(_dataset(10), gate_with_stub,
                                    ["stub"], slo_ms=50.0, max_items=4)
    assert report.n_items == 4
    assert report.backends["stub"]["n_decided"] == 4
