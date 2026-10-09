"""Slice 069 — route explanation."""

from __future__ import annotations

import pytest

from hugrgate import (Backend, BackendRegistry, DecisionPolicy, DecisionResult,
                      DecisionSpec)
from hugrgate.ladder import LadderRung
from hugrgate.routing import (LadderRouterV2, OUTCOME_PHRASES, RoutingOptions,
                              explain_decision, explain_plan, explain_route)
from hugrgate.routing.architecture import (RungMode, RungNode, RoutingDecision,
                                            RoutingPlan)


class ExBackend(Backend):
    def __init__(self, name, prob=0.95, latency=200.0):
        self.name = name
        self._prob = prob
        self._latency = latency

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        n = len(spec.options)
        rest = (1.0 - self._prob) / max(n - 1, 1)
        return DecisionResult(
            value="a", probability=self._prob,
            distribution={o: (self._prob if o == "a" else rest)
                          for o in spec.options},
            backend=self.name)

    def estimated_latency(self):
        return self._latency


def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


# -- plan explanation --------------------------------------------------------------------

def test_explain_plan_narrates_rungs_and_why():
    plan = RoutingPlan(
        nodes=[RungNode("cheap", 0.8, 100.0, why="cheapest first"),
               RungNode("strong", 0.9)],
        strategy=RungMode.SERIAL, created_by="test",
        rationale=["built for the test"])
    text = explain_plan(plan)
    assert plan.fingerprint in text
    assert "'cheap'" in text and "'strong'" in text
    assert "gate 0.80" in text
    assert "latency budget 100ms" in text
    assert "cheapest first" in text
    assert "built for the test" in text


def test_explain_empty_plan():
    text = explain_plan(RoutingPlan(nodes=[], created_by="test"))
    assert "empty" in text


# -- route explanation ---------------------------------------------------------------------

def test_explain_route_from_real_climb():
    reg = BackendRegistry()
    reg.register(ExBackend("slowpoke", prob=0.5, latency=500.0))
    reg.register(ExBackend("winner", prob=0.99, latency=5.0))
    router = LadderRouterV2(
        reg, rungs=[LadderRung("ghost", 0.9),
                    LadderRung("slowpoke", 0.9),
                    LadderRung("winner", 0.9)])
    won = router.decide({}, spec(), DecisionPolicy(minimum_probability=0.9))
    trace = won.metadata["ladder_trace"]
    text = explain_route(trace, router.last_plan, won.metadata["ladder_rung"])
    assert "'ghost'" in text and "not in the registry" in text
    assert "'slowpoke'" in text and "below its confidence gate" in text
    assert "'winner'" in text and "cleared its gate" in text
    assert "Winner: 'winner'" in text
    assert "Summary:" in text
    # no raw state values leak (state was empty here; assert the mechanism
    # on a non-empty state below)


def test_explanation_never_leaks_state_values():
    reg = BackendRegistry()
    reg.register(ExBackend("b", prob=0.99))
    router = LadderRouterV2(reg, rungs=[LadderRung("b", 0.9)])
    secret = "super-secret-value-12345"
    won = router.decide({"token": secret}, spec())
    text = explain_route(won.metadata["ladder_trace"], router.last_plan,
                         won.metadata["ladder_rung"])
    assert secret not in text
    assert explain_plan(router.last_plan).find(secret) == -1


def test_explain_empty_audit():
    assert explain_route([]) == "No rungs were attempted."


def test_all_outcomes_have_phrases():
    from hugrgate import ladder as L
    outcomes = [v for k, v in vars(L).items()
                if k.startswith("RUNG_") and isinstance(v, str)]
    assert outcomes, "expected RUNG_* outcome constants"
    for outcome in outcomes:
        assert outcome in OUTCOME_PHRASES, outcome


def test_explain_decision_ties_it_together():
    reg = BackendRegistry()
    reg.register(ExBackend("b", prob=0.99))
    router = LadderRouterV2(reg, rungs=[LadderRung("b", 0.9)])
    plan, ctx = router.build_plan({"x": 1}, spec())
    from hugrgate.routing import SerialPlanExecutor
    decision = SerialPlanExecutor().execute(router, plan, {"x": 1}, ctx)
    assert isinstance(decision, RoutingDecision)
    text = explain_decision(decision)
    assert "Decision:" in text and "'b'" in text
    assert "p=0.990" in text
