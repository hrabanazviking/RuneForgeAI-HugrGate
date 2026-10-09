"""Slice 109 — Mixture-of-experts router.

A gating network routes each input state to the experts that are
right in that region. Centerpiece: on two-region data the router
sends region-A inputs to expert A and region-B inputs to expert B,
and the MoE decision follows the routed expert.
"""

from __future__ import annotations

import pytest
from ensemble_fakes import ConstantBackend

from hugrgate import DecisionSpec
from hugrgate.ensemble import Ensemble, ExpertRouter, moe_combine
from hugrgate.ensemble.base import MemberVote, StrategyContext
from hugrgate.errors import BackendError, PolicyError

BIN = DecisionSpec(type="binary", statement="s")


def _vote(name, value, pt):
    dist = {"true": pt, "false": 1 - pt} if value == "true" else \
        {"true": 1 - pt, "false": pt}
    return MemberVote(backend=name, value=value, probability=pt,
                      distribution=dist)


def _regions(n=20):
    """expert_a right for x<0.5, expert_b right for x>=0.5."""
    states, samples, labels = [], [], []
    for i in range(n):
        x = i / float(n)
        states.append({"x": x})
        if x < 0.5:
            samples.append([_vote("expert_a", "true", 0.9),
                            _vote("expert_b", "false", 0.9)])
        else:
            samples.append([_vote("expert_a", "false", 0.9),
                            _vote("expert_b", "true", 0.9)])
        labels.append("true")
    return states, samples, labels


def _fitted_router(top_k=1):
    states, samples, labels = _regions()
    return ExpertRouter(["expert_a", "expert_b"], ["x"],
                        top_k=top_k).fit(states, samples, labels, BIN)


# --- success -----------------------------------------------------------------

def test_router_learns_regions():
    router = _fitted_router()
    assert router.fitted
    gates_a = router.route({"x": 0.1})
    gates_b = router.route({"x": 0.9})
    assert gates_a["expert_a"] > 0.85
    assert gates_b["expert_b"] > 0.85
    assert abs(sum(gates_a.values()) - 1.0) < 1e-9


def test_topk_routing_is_decisive():
    router = _fitted_router(top_k=1)
    assert router.route_topk({"x": 0.1}) == {"expert_a": 1.0}
    assert router.route_topk({"x": 0.9}) == {"expert_b": 1.0}
    both = _fitted_router(top_k=2).route_topk({"x": 0.1})
    assert set(both) == {"expert_a", "expert_b"}
    assert abs(sum(both.values()) - 1.0) < 1e-9


def test_moe_follows_the_routed_expert():
    router = _fitted_router(top_k=1)
    # expert_a always says true, expert_b always says false;
    # the router decides who is heard per region.
    a = ConstantBackend("expert_a", "true", {"true": 0.9, "false": 0.1})
    b = ConstantBackend("expert_b", "false", {"true": 0.1, "false": 0.9})
    ens = Ensemble([a, b], strategy="moe").attach(router)
    region_a = ens.evaluate({"x": 0.1}, BIN)
    region_b = ens.evaluate({"x": 0.9}, BIN)
    assert region_a.value == "true"   # routed to expert_a
    assert region_b.value == "false"  # routed to expert_b
    assert region_a.metadata["ensemble"]["strategy"] == "moe"
    assert region_a.metadata["ensemble"]["gates"] == {"expert_a": 1.0}
    assert region_a.metadata["ensemble"]["routed_experts"] == ["expert_a"]


def test_extract_handles_missing_and_nonnumeric():
    router = _fitted_router()
    assert router.extract({}) == [0.0]
    assert router.extract({"x": "hot"}) == [0.0]
    assert router.extract({"x": float("inf")}) == [0.0]
    assert router.extract({"x": 2.5}) == [2.5]


def test_fit_is_deterministic():
    states, samples, labels = _regions()
    r1 = ExpertRouter(["expert_a", "expert_b"], ["x"]).fit(
        states, samples, labels, BIN)
    r2 = ExpertRouter(["expert_a", "expert_b"], ["x"]).fit(
        states, samples, labels, BIN)
    assert r1._w == r2._w and r1._b == r2._b


def test_to_dict():
    d = _fitted_router().to_dict()
    assert d["members"] == ["expert_a", "expert_b"]
    assert d["feature_names"] == ["x"]
    assert d["fitted"] is True


# --- failure -----------------------------------------------------------------

def test_combine_needs_fitted_router_and_state():
    votes = [_vote("expert_a", "true", 0.9)]
    with pytest.raises(BackendError, match="fitted ExpertRouter"):
        moe_combine(votes, StrategyContext(spec=BIN, fitted=None))
    with pytest.raises(BackendError, match="fitted ExpertRouter"):
        moe_combine(votes, StrategyContext(
            spec=BIN, fitted=ExpertRouter(["expert_a"], ["x"])))
    with pytest.raises(BackendError, match="input state"):
        moe_combine(votes, StrategyContext(spec=BIN,
                                           fitted=_fitted_router()))


def test_router_validation():
    states, samples, labels = _regions()
    with pytest.raises(PolicyError, match="at least one member"):
        ExpertRouter([], ["x"])
    with pytest.raises(PolicyError, match="unique"):
        ExpertRouter(["a", "a"], ["x"])
    with pytest.raises(PolicyError, match="at least one feature"):
        ExpertRouter(["a"], [])
    with pytest.raises(PolicyError, match="top_k"):
        ExpertRouter(["a", "b"], ["x"], top_k=3)
    with pytest.raises(PolicyError, match="lengths disagree"):
        ExpertRouter(["a"], ["x"]).fit(states[:-1], samples, labels, BIN)
    with pytest.raises(PolicyError, match="labeled samples"):
        ExpertRouter(["a"], ["x"]).fit([], [], [], BIN)
    with pytest.raises(PolicyError, match="outside the spec space"):
        ExpertRouter(["a"], ["x"]).fit(
            states, samples, ["maybe"] * len(labels), BIN)
    with pytest.raises(PolicyError, match="top_k must be >= 1"):
        _fitted_router().route_topk({"x": 0.1}, k=0)


def test_route_before_fit():
    with pytest.raises(BackendError, match="before fit"):
        ExpertRouter(["a"], ["x"]).route({"x": 0.1})


def test_numeric_spec_rejected():
    numeric = DecisionSpec(type="numeric", minimum=0.0, maximum=1.0)
    with pytest.raises(BackendError, match="discrete spec"):
        moe_combine([], StrategyContext(spec=numeric,
                                        fitted=_fitted_router(),
                                        state={"x": 0.1}))


# --- boundary ----------------------------------------------------------------

def test_topk_option_override():
    router = _fitted_router(top_k=2)
    a = ConstantBackend("expert_a", "true", {"true": 0.9, "false": 0.1})
    b = ConstantBackend("expert_b", "false", {"true": 0.1, "false": 0.9})
    ens = Ensemble([a, b], strategy="moe",
                   strategy_options={"top_k": 1}).attach(router)
    result = ens.evaluate({"x": 0.1}, BIN)
    assert result.metadata["ensemble"]["top_k"] == 1
    assert result.value == "true"


def test_candidates_restrict_routing():
    router = _fitted_router()
    gates = router.route({"x": 0.1}, candidates=["expert_b"])
    assert set(gates) == {"expert_b"}
    with pytest.raises(BackendError, match="no candidates"):
        router.route({"x": 0.1}, candidates=[])
