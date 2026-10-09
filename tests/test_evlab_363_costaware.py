"""Slice 363 — Cost-aware evaluation.

Covers: the cost cascade (metadata actuals > estimated_cost >
CostModel), Pareto frontier math (dominated/excluded, ties kept),
best_under_budget / cheapest_at_accuracy queries, zero-cost handling
(None, not crash), negative-rate rejection, and serialization
round-trip.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionSpec
from hugrgate.backend import Backend
from hugrgate.errors import EvalError
from hugrgate.evlab import (
    CostModel,
    CostReport,
    cost_aware_evaluate,
    pareto_frontier,
)
from hugrgate.result import DecisionResult


class SpendyBackend(Backend):
    """Reports true per-decision spend via result metadata."""

    def __init__(self, name, value, cost):
        self.name = name
        self.value = value
        self._cost = cost

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        options = spec.options or ["a", "b"]
        dist = {o: (1.0 if o == self.value else 0.0) for o in options}
        return DecisionResult(
            value=self.value, probability=1.0,
            distribution=dist,
            metadata={"cost": self._cost})


class EstimatedBackend(Backend):
    """Declares spend via estimated_cost()."""

    def __init__(self, name, value, cost):
        self.name = name
        self.value = value
        self._cost = cost

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def estimated_cost(self):
        return self._cost

    def evaluate(self, state, spec, context=None):
        options = spec.options or ["a", "b"]
        dist = {o: (1.0 if o == self.value else 0.0) for o in options}
        return DecisionResult(value=self.value, probability=1.0,
                              distribution=dist)


def _dataset(n=40):
    return {
        "name": "cost-smoke",
        "version": "1.0.0",
        "spec": DecisionSpec(type="categorical",
                             options=["a", "b"]).to_dict(),
        "items": [{"state": {"x": i}, "expected": "a"} for i in range(n)],
    }


def test_actual_costs_win_the_cascade(gate_with_stub):
    gate_with_stub.register(SpendyBackend("spendy", "a", 0.02))
    report = cost_aware_evaluate(_dataset(), gate_with_stub, ["spendy"])
    info = report.backends["spendy"]
    assert info["cost_source"] == "actual"
    assert info["total_cost"] == pytest.approx(0.8)
    assert info["accuracy"] == pytest.approx(1.0)
    assert info["accuracy_per_cost"] == pytest.approx(1.0 / 0.8)
    assert info["cost_per_correct"] == pytest.approx(0.8 / 40)


def test_estimated_cost_fallback(gate_with_stub):
    gate_with_stub.register(EstimatedBackend("est", "a", 0.05))
    report = cost_aware_evaluate(_dataset(), gate_with_stub, ["est"])
    info = report.backends["est"]
    assert info["cost_source"] == "estimated"
    assert info["total_cost"] == pytest.approx(2.0)


def test_model_rate_fallback(gate_with_stub):
    model = CostModel(rates={"stub": 0.01}, currency="EUR")
    report = cost_aware_evaluate(_dataset(), gate_with_stub, ["stub"],
                                 cost_model=model)
    info = report.backends["stub"]
    assert info["cost_source"] == "model"
    assert info["total_cost"] == pytest.approx(0.4)
    assert report.currency == "EUR"


def test_zero_cost_gives_none_efficiencies(gate_with_stub):
    report = cost_aware_evaluate(_dataset(), gate_with_stub, ["stub"])
    info = report.backends["stub"]
    assert info["total_cost"] == pytest.approx(0.0)
    assert info["accuracy_per_cost"] is None
    # cost_per_correct is still well-defined at zero spend.
    assert info["cost_per_correct"] == pytest.approx(0.0)


def test_negative_rate_rejected():
    with pytest.raises(EvalError):
        CostModel(rates={"x": -1.0}).rate_for("x")


def test_pareto_frontier_math():
    points = {
        "cheap-good": (1.0, 0.9),
        "pricey-best": (5.0, 0.95),
        "dominated": (3.0, 0.8),   # worse than cheap-good on both axes
        "twin": (1.0, 0.9),        # identical: not strictly dominated
    }
    frontier = pareto_frontier(points)
    assert "dominated" not in frontier
    assert set(frontier) == {"cheap-good", "pricey-best", "twin"}


def test_pareto_in_report(gate_with_stub):
    gate_with_stub.register(SpendyBackend("spendy", "a", 0.10))
    gate_with_stub.register(EstimatedBackend("est", "b", 0.01))
    model = CostModel(rates={"stub": 0.0})
    report = cost_aware_evaluate(_dataset(), gate_with_stub,
                                 ["stub", "spendy", "est"],
                                 cost_model=model)
    # stub: acc 1.0 cost 0 — dominates everyone.
    assert report.pareto == ["stub"]


def test_best_under_budget(gate_with_stub):
    gate_with_stub.register(SpendyBackend("spendy", "a", 0.10))
    gate_with_stub.register(EstimatedBackend("mid", "a", 0.01))
    report = cost_aware_evaluate(_dataset(), gate_with_stub,
                                 ["spendy", "mid"])
    name, acc = report.best_under_budget(1.0)
    assert name == "mid"  # spendy costs 4.0 > budget
    assert acc == pytest.approx(1.0)
    assert report.best_under_budget(0.001) == (None, None)
    with pytest.raises(EvalError):
        report.best_under_budget(-1.0)


def test_cheapest_at_accuracy(gate_with_stub):
    gate_with_stub.register(SpendyBackend("spendy", "a", 0.10))
    gate_with_stub.register(EstimatedBackend("mid", "a", 0.01))
    report = cost_aware_evaluate(_dataset(), gate_with_stub,
                                 ["spendy", "mid"])
    name, cost = report.cheapest_at_accuracy(0.9)
    assert name == "mid"
    assert cost == pytest.approx(0.4)
    with pytest.raises(EvalError):
        report.cheapest_at_accuracy(1.5)
    empty = CostReport(backends={"x": {"accuracy": 0.5,
                                       "total_cost": 1.0}},
                       pareto=["x"], currency="USD", n_items=10)
    assert empty.cheapest_at_accuracy(0.9) == (None, None)


def test_cost_model_roundtrip():
    model = CostModel(rates={"a": 0.5}, default_rate=0.1, currency="EUR")
    assert CostModel.from_dict(model.to_dict()).to_dict() == \
        model.to_dict()


def test_report_roundtrip(gate_with_stub):
    gate_with_stub.register(EstimatedBackend("est", "a", 0.05))
    report = cost_aware_evaluate(_dataset(), gate_with_stub, ["est"])
    clone = CostReport.from_dict(report.to_dict())
    assert clone.to_dict() == report.to_dict()
    assert clone.best_under_budget(10.0)[0] == "est"
