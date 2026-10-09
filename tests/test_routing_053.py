"""Slice 053 — per-request ladder synthesis."""

from __future__ import annotations

import pytest

from hugrgate import (Abstention, Backend, BackendRegistry, DecisionPolicy,
                      DecisionResult, DecisionSpec)
from hugrgate.ladder import LadderRung
from hugrgate.routing import (LadderRouterV2, LadderSynthesizer,
                              QOS_DEPTH_CAPS, RouterContext, RoutingOptions,
                              RungMode, score_capability)


class SynBackend(Backend):
    def __init__(self, name, prob=0.9, cost=0.0, latency=10.0,
                 spec_types=("categorical",), accuracy=None,
                 calibrated=False):
        self.name = name
        self._prob = prob
        self._cost = cost
        self._latency = latency
        self._spec_types = tuple(spec_types)
        self._accuracy = accuracy
        self._calibrated = calibrated

    def capabilities(self):
        caps = {"spec_types": list(self._spec_types)}
        if self._accuracy is not None:
            caps["accuracy"] = self._accuracy
        return caps

    def supports(self, spec):
        return spec.type in self._spec_types

    def evaluate(self, state, spec, context=None):
        n = len(spec.options)
        rest = (1.0 - self._prob) / max(n - 1, 1)
        return DecisionResult(
            value="a", probability=self._prob,
            distribution={o: (self._prob if o == "a" else rest)
                          for o in spec.options},
            backend=self.name)

    def estimated_cost(self):
        return self._cost

    def estimated_latency(self):
        return self._latency

    def calibration_info(self):
        return {"calibrated": self._calibrated}


def reg_of(*bs):
    r = BackendRegistry()
    for b in bs:
        r.register(b)
    return r


def ctx(policy=None, options=None):
    return RouterContext.from_request(
        {"x": 1}, DecisionSpec(type="categorical", options=["a", "b"]),
        policy or DecisionPolicy(), options or RoutingOptions())


# -- capability heuristic -------------------------------------------------------

def test_score_capability_rewards_evidence():
    c = ctx()
    plain = SynBackend("plain")
    assert 0.0 < score_capability(plain, c) <= 1.0
    accurate = SynBackend("acc", accuracy=0.95)
    assert score_capability(accurate, c) >= score_capability(plain, c)
    cal = SynBackend("cal", calibrated=True)
    assert score_capability(cal, c) > score_capability(plain, c)
    wrong = SynBackend("wrong", spec_types=("ranking",))
    assert score_capability(wrong, c) == 0.0


# -- synthesis ------------------------------------------------------------------

def test_qos_changes_ladder_order():
    reg = reg_of(SynBackend("slow-smart", cost=0.5, latency=800.0,
                            accuracy=0.99),
                 SynBackend("fast-cheap", cost=0.001, latency=5.0))
    be = LadderSynthesizer(reg).plan(
        ctx(options=RoutingOptions(qos="best_effort")))
    crit = LadderSynthesizer(reg).plan(
        ctx(options=RoutingOptions(qos="critical")))
    assert [n.backend_name for n in be.nodes][0] == "fast-cheap"
    assert [n.backend_name for n in crit.nodes][0] == "slow-smart"


def test_depth_caps_by_qos():
    reg = reg_of(*[SynBackend(f"b{i}") for i in range(10)])
    for qos, cap in QOS_DEPTH_CAPS.items():
        plan = LadderSynthesizer(reg).plan(
            ctx(options=RoutingOptions(qos=qos)))
        assert len(plan.nodes) <= cap, qos
    be = LadderSynthesizer(reg).plan(
        ctx(options=RoutingOptions(qos="best_effort")))
    assert len(be.nodes) == QOS_DEPTH_CAPS["best_effort"]


def test_latency_budget_split_across_plan():
    reg = reg_of(SynBackend("a"), SynBackend("b"), SynBackend("c"))
    plan = LadderSynthesizer(reg).plan(
        ctx(DecisionPolicy(maximum_latency_ms=300.0)))
    budgets = [n.latency_budget_ms for n in plan.nodes]
    assert all(b == pytest.approx(100.0) for b in budgets)
    assert sum(budgets) <= 300.0 + 1e-9


def test_strategy_flows_into_plan_and_nodes():
    reg = reg_of(SynBackend("a"))
    plan = LadderSynthesizer(reg).plan(
        ctx(options=RoutingOptions(strategy="parallel")))
    assert plan.strategy is RungMode.PARALLEL
    assert plan.nodes[0].mode is RungMode.PARALLEL


def test_rationale_and_why_are_populated():
    reg = reg_of(SynBackend("a", cost=0.02, latency=20.0))
    plan = LadderSynthesizer(reg).plan(ctx())
    assert plan.rationale and plan.nodes[0].why
    assert "blended_score" in plan.nodes[0].params


def test_empty_synthesis_abstains_end_to_end():
    reg = reg_of(SynBackend("x", spec_types=("ranking",)))
    router = LadderRouterV2(
        reg, ladders={"categorical": [LadderRung("x")]},
        planner=LadderSynthesizer(reg))
    with pytest.raises(Abstention):
        router.decide({}, DecisionSpec(type="categorical", options=["a", "b"]))


def test_synthesis_end_to_end_picks_best_for_qos():
    reg = reg_of(SynBackend("cheap-weak", prob=0.5, cost=0.0),
                 SynBackend("pricey-strong", prob=0.99, cost=0.4,
                            accuracy=0.98))
    router = LadderRouterV2(
        reg, ladders={"categorical": [LadderRung("cheap-weak")]},
        planner=LadderSynthesizer(reg))
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    policy = DecisionPolicy(minimum_probability=0.8)
    won = router.decide(
        {}, spec, policy, options=RoutingOptions(qos="critical"))
    assert won.backend == "pricey-strong"
    assert won.metadata["routing_plan"]["created_by"] == "LadderSynthesizer"
