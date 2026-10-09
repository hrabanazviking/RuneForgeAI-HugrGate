"""Slice 365 — Energy-aware evaluation.

Covers: model-rate totals, measured energy via MockPowerSource
(power x latency), mixed fallback when samples fail, efficiency and
budget queries, Pareto reuse, CO2e math and validation, negative-rate
rejection, and serialization round-trip.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionSpec
from hugrgate.edge.power import MockPowerSource
from hugrgate.errors import EvalError
from hugrgate.evlab import (
    EnergyModel,
    EnergyReport,
    co2e_grams,
    energy_aware_evaluate,
)


def _dataset(n=10):
    return {
        "name": "nrg-smoke",
        "version": "1.0.0",
        "spec": DecisionSpec(type="categorical",
                             options=["a", "b"]).to_dict(),
        "items": [{"state": {"x": i}, "expected": "a"} for i in range(n)],
    }


def test_model_rates(gate_with_stub):
    model = EnergyModel(rates_mj={"stub": 2.0})
    report = energy_aware_evaluate(_dataset(), gate_with_stub, ["stub"],
                                   energy_model=model)
    info = report.backends["stub"]
    assert info["energy_source"] == "model"
    assert info["total_energy_mj"] == pytest.approx(20.0)
    assert info["energy_per_decision_mj"] == pytest.approx(2.0)
    assert info["accuracy"] == pytest.approx(1.0)
    # 1.0 accuracy / 0.02 J
    assert info["accuracy_per_joule"] == pytest.approx(50.0)
    assert info["n_measured"] == 0


def test_measured_energy(gate_with_stub):
    from tests.conftest import StubBackend
    # Constant 1000 mW; latency is stub-instant (~0 ms) so we give the
    # backend a real delay to make energy nonzero and check the math:
    # E = 1000 mW * latency_s.
    gate_with_stub.register(StubBackend(name="slow", value="a",
                                        delay=0.02))
    source = MockPowerSource([1000.0] * 1000)
    report = energy_aware_evaluate(_dataset(5), gate_with_stub,
                                   ["slow"], power_source=source)
    info = report.backends["slow"]
    assert info["energy_source"] == "measured"
    assert info["n_measured"] == 5
    lat_s = info["total_energy_mj"] / 1000.0
    assert lat_s > 0
    # Energy tracks the real latency: 5 x ~20ms x 1000mW ~= 100 mJ.
    assert info["total_energy_mj"] == pytest.approx(100.0, rel=0.5)
    assert info["energy_per_decision_mj"] == pytest.approx(20.0, rel=0.5)


def test_mixed_fallback_when_samples_fail(gate_with_stub):
    model = EnergyModel(rates_mj={"stub": 3.0})
    # Script of Nones: every sample fails -> pure model fallback.
    source = MockPowerSource([None, None])
    report = energy_aware_evaluate(_dataset(4), gate_with_stub, ["stub"],
                                   energy_model=model,
                                   power_source=source)
    info = report.backends["stub"]
    assert info["energy_source"] == "model"
    assert info["total_energy_mj"] == pytest.approx(12.0)


def test_most_efficient_and_budget(gate_with_stub):
    model = EnergyModel(rates_mj={"stub": 1.0})
    report = energy_aware_evaluate(_dataset(), gate_with_stub, ["stub"],
                                   energy_model=model)
    name, eff = report.most_efficient()
    assert name == "stub"
    assert eff == pytest.approx(100.0)  # 1.0 / 0.01 J
    best, acc = report.best_under_energy_budget(10.0)
    assert best == "stub" and acc == pytest.approx(1.0)
    assert report.best_under_energy_budget(0.5) == (None, None)
    with pytest.raises(EvalError):
        report.best_under_energy_budget(-1.0)


def test_pareto_reuse(gate_with_stub):
    from tests.conftest import StubBackend
    gate_with_stub.register(StubBackend(name="hog", value="a"))
    model = EnergyModel(rates_mj={"stub": 1.0, "hog": 99.0})
    report = energy_aware_evaluate(_dataset(), gate_with_stub,
                                   ["stub", "hog"],
                                   energy_model=model)
    # Same accuracy, stub is cheaper: hog is dominated.
    assert report.pareto == ["stub"]


def test_co2e_math():
    # 3.6 MJ = 1 Wh = 0.001 kWh -> 0.4 g at 400 g/kWh.
    assert co2e_grams(3_600_000.0) == pytest.approx(0.4)
    assert co2e_grams(0.0) == pytest.approx(0.0)
    with pytest.raises(EvalError):
        co2e_grams(-1.0)
    with pytest.raises(EvalError):
        co2e_grams(100.0, grid_intensity_g_per_kwh=0.0)


def test_negative_rate_rejected():
    with pytest.raises(EvalError):
        EnergyModel(rates_mj={"x": -2.0}).rate_for("x")


def test_empty_items_rejected(gate_with_stub):
    ds = _dataset(5)
    ds["items"] = []
    with pytest.raises(EvalError):
        energy_aware_evaluate(ds, gate_with_stub, ["stub"])


def test_model_roundtrip():
    model = EnergyModel(rates_mj={"a": 1.5}, default_rate_mj=0.5)
    assert EnergyModel.from_dict(model.to_dict()).to_dict() == \
        model.to_dict()


def test_report_roundtrip(gate_with_stub):
    model = EnergyModel(rates_mj={"stub": 2.0})
    report = energy_aware_evaluate(_dataset(), gate_with_stub, ["stub"],
                                   energy_model=model)
    clone = EnergyReport.from_dict(report.to_dict())
    assert clone.to_dict() == report.to_dict()
    assert clone.most_efficient()[0] == "stub"
