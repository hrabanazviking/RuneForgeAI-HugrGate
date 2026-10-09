"""Slice 054 — capability scoring."""

from __future__ import annotations

import pytest

from hugrgate import Backend, BackendRegistry, DecisionSpec
from hugrgate.routing import (
    CAPABILITY_WEIGHTS,
    CapabilityScorer,
    RouterContext,
    RungBuilder,
    score_capability,
)


class CapBackend(Backend):
    def __init__(self, name, spec_types=("categorical",), caps=None,
                 cal=None):
        self.name = name
        self._spec_types = tuple(spec_types)
        self._caps = caps or {}
        self._cal = cal or {}

    def capabilities(self):
        return dict(self._caps,
                    spec_types=list(self._spec_types))

    def supports(self, spec):
        return spec.type in self._spec_types

    def evaluate(self, state, spec, context=None):  # pragma: no cover
        raise NotImplementedError

    def calibration_info(self):
        return dict(self._cal)


def ctx(spec=None):
    return RouterContext.from_request(
        {}, spec or DecisionSpec(type="categorical", options=["a", "b"]))


def test_unsupported_scores_zero_with_reason():
    s = CapabilityScorer().score(CapBackend("x", spec_types=("ranking",)),
                                 ctx())
    assert s.value == 0.0
    assert any("does not support" in r for r in s.reasons)
    assert s.factors["support"] == 0.0


def test_quality_claims_raise_score_monotonically():
    c = ctx()
    low = CapabilityScorer().score(CapBackend("low", caps={"accuracy": 0.6}),
                                   c)
    high = CapabilityScorer().score(CapBackend("high", caps={"accuracy": 0.95}),
                                    c)
    assert high.value > low.value
    assert any("accuracy=0.95" in r for r in high.reasons)


def test_calibration_bonus_and_ece_discount():
    c = ctx()
    plain = CapabilityScorer().score(CapBackend("plain"), c)
    cal = CapabilityScorer().score(CapBackend("cal", cal={"calibrated": True}),
                                   c)
    assert cal.value > plain.value
    noisy = CapabilityScorer().score(
        CapBackend("noisy", cal={"calibrated": True, "ece": 0.4}), c)
    assert noisy.value < cal.value
    assert any("calibration error" in r for r in noisy.reasons)


def test_feature_coverage_factor():
    spec = DecisionSpec(type="categorical", options=["a", "b"],
                        metadata={"requires_features": ["x", "y", "z"]})
    c = ctx(spec)
    partial = CapabilityScorer().score(
        CapBackend("p", caps={"features": ["x"]}), c)
    full = CapabilityScorer().score(
        CapBackend("f", caps={"features": ["x", "y", "z"]}), c)
    assert partial.factors["features"] == pytest.approx(1 / 3, abs=1e-3)
    assert full.factors["features"] == 1.0
    assert full.value > partial.value


def test_capacity_unfit_scores_zero_capacity():
    spec = DecisionSpec(type="categorical",
                        options=[f"o{i}" for i in range(10)])
    c = ctx(spec)
    small = CapabilityScorer().score(
        CapBackend("s", caps={"limits": {"max_options": 4}}), c)
    assert small.factors["capacity"] == 0.0
    assert any("unfit" in r for r in small.reasons)


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        CapabilityScorer(weights={"quality": 0.5})


def test_score_value_always_in_unit_interval():
    c = ctx()
    for caps in ({}, {"accuracy": 1.0}, {"accuracy": 0.0, "features": []}):
        s = CapabilityScorer().score(CapBackend("b", caps=caps), c)
        assert 0.0 <= s.value <= 1.0
        assert abs(sum(s.factors[k] * CAPABILITY_WEIGHTS[k]
                       for k in CAPABILITY_WEIGHTS) - s.value) < 1e-3


def test_score_capability_wrapper_agrees():
    c = ctx()
    b = CapBackend("b", caps={"accuracy": 0.9})
    assert score_capability(b, c) == CapabilityScorer().score(b, c).value


def test_builder_capability_ordering():
    reg = BackendRegistry()
    reg.register(CapBackend("dumb", caps={"accuracy": 0.55}))
    reg.register(CapBackend("smart", caps={"accuracy": 0.99}))
    nodes = RungBuilder(order="capability").build(reg, ctx())
    assert [n.backend_name for n in nodes] == ["smart", "dumb"]


def test_synthesis_uses_scorer_reasons():
    # blended ordering still prefers the accurate backend under critical QoS
    from hugrgate.routing import LadderSynthesizer, RoutingOptions
    reg = BackendRegistry()
    reg.register(CapBackend("dumb", caps={"accuracy": 0.55}))
    reg.register(CapBackend("smart", caps={"accuracy": 0.99}))
    plan = LadderSynthesizer(reg).plan(
        RouterContext.from_request(
            {}, DecisionSpec(type="categorical", options=["a", "b"]),
            options=RoutingOptions(qos="critical")))
    assert plan.nodes[0].backend_name == "smart"
    assert plan.nodes[0].params["capability"] > 0.5
