"""Slice 055 — confidence-aware routing (incl. statistical validation)."""

from __future__ import annotations

import random

import pytest

from hugrgate import Backend, BackendRegistry, DecisionPolicy, DecisionSpec
from hugrgate.routing import (
    CalibrationTracker,
    ConfidenceAwarePlanner,
    LadderSynthesizer,
    RouterContext,
    adjusted_gate,
)
from hugrgate.routing.architecture import RoutingPlan, RungNode


class CalBackend(Backend):
    def __init__(self, name, ece=0.0, spec_types=("categorical",)):
        self.name = name
        self._ece = ece
        self._spec_types = tuple(spec_types)

    def capabilities(self):
        return {"spec_types": list(self._spec_types)}

    def supports(self, spec):
        return spec.type in self._spec_types

    def evaluate(self, state, spec, context=None):  # pragma: no cover
        raise NotImplementedError

    def calibration_info(self):
        return {"calibrated": self._ece == 0.0, "ece": self._ece}


def ctx():
    return RouterContext.from_request(
        {}, DecisionSpec(type="categorical", options=["a", "b"]),
        DecisionPolicy(minimum_probability=0.8))


# -- unit behavior ---------------------------------------------------------------

def test_adjusted_gate_widens_and_clamps():
    assert adjusted_gate(0.8, 0.0) == 0.8
    assert adjusted_gate(0.8, 0.15) == pytest.approx(0.95)
    assert adjusted_gate(0.9, 0.5) == 1.0  # clamped, never exceeds 1
    with pytest.raises(ValueError):
        adjusted_gate(1.2, 0.0)
    with pytest.raises(ValueError):
        adjusted_gate(0.5, -0.1)


def test_tracker_rejects_bad_inputs():
    t = CalibrationTracker()
    with pytest.raises(ValueError):
        t.record("b", 1.5, True)
    with pytest.raises(ValueError):
        CalibrationTracker(n_bins=0)
    assert t.ece("unknown") == 0.0
    assert t.samples("unknown") == 0


def test_planner_widens_gates_by_declared_ece():
    reg = BackendRegistry()
    reg.register(CalBackend("honest", ece=0.0))
    reg.register(CalBackend("cocky", ece=0.2))
    inner = LadderSynthesizer(reg)
    planner = ConfidenceAwarePlanner(inner, reg)
    plan = planner.plan(ctx())
    gates = {n.backend_name: n.min_confidence for n in plan.nodes}
    assert gates["honest"] == pytest.approx(0.8)
    assert gates["cocky"] == pytest.approx(1.0)
    cocky = next(n for n in plan.nodes if n.backend_name == "cocky")
    assert "ece=0.200" in cocky.why
    assert cocky.params["base_gate"] == pytest.approx(0.8)
    assert plan.created_by.endswith("+confidence")


def test_tracker_ece_overrides_declared_when_enough_samples():
    reg = BackendRegistry()
    reg.register(CalBackend("b", ece=0.3))  # declared pessimistic
    tracker = CalibrationTracker()
    rng = random.Random(7)
    for _ in range(200):  # actually well calibrated at 0.8
        tracker.record("b", 0.8, rng.random() < 0.8)
    planner = ConfidenceAwarePlanner(LadderSynthesizer(reg), reg,
                                     tracker=tracker, min_samples=50)
    plan = planner.plan(ctx())
    gate = next(n for n in plan.nodes
                if n.backend_name == "b").min_confidence
    assert gate == pytest.approx(0.8, abs=0.06)  # measured, not declared


def test_planner_keeps_unknown_backends_untouched():
    class FixedPlan:
        def plan(self, ctx):
            return RoutingPlan(nodes=[RungNode("ghost", 0.7)],
                               created_by="fixed")

    plan = ConfidenceAwarePlanner(FixedPlan(), BackendRegistry()).plan(ctx())
    assert plan.nodes[0].min_confidence == 0.7


# -- statistical validation on controlled data -----------------------------------

def test_ece_detects_overconfidence_on_controlled_data():
    """Backend reports 0.9, truly correct 70%: ECE must land near 0.2."""
    rng = random.Random(20261009)
    tracker = CalibrationTracker(n_bins=10)
    n = 5000
    for _ in range(n):
        tracker.record("cocky", 0.9, rng.random() < 0.7)
    ece = tracker.ece("cocky")
    assert ece == pytest.approx(0.2, abs=0.03), f"ece={ece}"
    # gate widening responds: 0.8 -> ~1.0 for this backend
    assert tracker.gate_for("cocky", 0.8) == pytest.approx(1.0, abs=0.03)


def test_ece_near_zero_for_calibrated_backend():
    """Reported p uniform in [0.5,1], correct ~ Bernoulli(p): ECE small."""
    rng = random.Random(42)
    tracker = CalibrationTracker(n_bins=10)
    n = 20000
    for _ in range(n):
        p = rng.uniform(0.5, 1.0)
        tracker.record("honest", p, rng.random() < p)
    ece = tracker.ece("honest")
    assert ece < 0.03, f"ece={ece}"
    assert tracker.gate_for("honest", 0.8) == pytest.approx(0.8, abs=0.03)


def test_empirical_coverage_at_gate():
    """Accepted-at-0.8 decisions from a calibrated backend are correct
    ~80%+ of the time (coverage assumption of the gate)."""
    rng = random.Random(99)
    correct = total = 0
    for _ in range(20000):
        p = rng.uniform(0.5, 1.0)
        if p >= 0.8:
            total += 1
            correct += rng.random() < p
    coverage = correct / total
    assert coverage == pytest.approx(0.9, abs=0.03), f"coverage={coverage}"
    assert coverage >= 0.8 - 0.02
