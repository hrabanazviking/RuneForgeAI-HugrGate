"""Slice 057 — cost-aware routing."""

from __future__ import annotations

import pytest

from hugrgate import (Abstention, Backend, BackendRegistry, DecisionPolicy,
                      DecisionResult, DecisionSpec)
from hugrgate.ladder import LadderRung
from hugrgate.routing import (CostAwarePlanner, CostLedger, DynamicRungPlanner,
                              LadderRouterV2, RouterContext, RoutingOptions,
                              budget_for)


class CostBackend(Backend):
    def __init__(self, name, cost=0.0, prob=0.95, actual_cost=None):
        self.name = name
        self._cost = cost
        self._prob = prob
        self._actual = actual_cost

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        n = len(spec.options)
        rest = (1.0 - self._prob) / max(n - 1, 1)
        result = DecisionResult(
            value="a", probability=self._prob,
            distribution={o: (self._prob if o == "a" else rest)
                          for o in spec.options},
            backend=self.name)
        if self._actual is not None:
            result.metadata["cost"] = self._actual
        return result

    def estimated_cost(self):
        return self._cost


def reg_of(*bs):
    r = BackendRegistry()
    for b in bs:
        r.register(b)
    return r


def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def ctx(policy=None, options=None):
    return RouterContext.from_request({}, spec(), policy or DecisionPolicy(),
                                      options or RoutingOptions())


# -- ledger ----------------------------------------------------------------------

def test_ledger_reserve_spend_remaining():
    ledger = CostLedger(1.0)
    assert ledger.remaining == 1.0
    assert ledger.can_afford(0.4)
    assert ledger.reserve("a", 0.4)
    assert ledger.remaining == pytest.approx(0.6)
    assert not ledger.can_afford(0.7)
    assert not ledger.reserve("b", 0.7)
    ledger.spend("a", 0.35)
    assert ledger.spent == pytest.approx(0.35)
    assert ledger.remaining == pytest.approx(0.25)
    with pytest.raises(ValueError):
        CostLedger(-1.0)
    with pytest.raises(ValueError):
        ledger.spend("a", -0.1)


def test_unbounded_ledger_affords_everything():
    ledger = CostLedger(None)
    assert ledger.remaining is None
    assert ledger.can_afford(1e9)
    assert ledger.reserve("x", 1e9)


def test_budget_for_prefers_options_over_policy():
    assert budget_for(ctx()) is None
    assert budget_for(ctx(DecisionPolicy(max_cost=0.5))) == 0.5
    assert budget_for(ctx(DecisionPolicy(max_cost=0.5),
                          RoutingOptions(max_cost=0.1))) == 0.1


# -- planner -----------------------------------------------------------------------

def test_planner_prunes_unaffordable_rungs():
    reg = reg_of(CostBackend("cheap", cost=0.1),
                 CostBackend("pricey", cost=0.9))
    planner = CostAwarePlanner(DynamicRungPlanner(reg), reg)
    plan = planner.plan(ctx(DecisionPolicy(max_cost=0.5)))
    assert [n.backend_name for n in plan.nodes] == ["cheap"]
    assert any("pruned 1 rung" in r for r in plan.rationale)
    assert plan.nodes[0].params["cost_estimate"] == 0.1


def test_cumulative_reservation_prunes_later_rungs():
    reg = reg_of(CostBackend("a", cost=0.3), CostBackend("b", cost=0.3),
                 CostBackend("c", cost=0.3))
    planner = CostAwarePlanner(DynamicRungPlanner(reg), reg)
    plan = planner.plan(ctx(DecisionPolicy(max_cost=0.5)))
    # 0.3 fits, next 0.3 would exceed 0.5 cumulatively
    assert [n.backend_name for n in plan.nodes] == ["a"]
    assert plan.ledger.reserved == pytest.approx(0.3)


def test_empty_cost_plan_abstains():
    reg = reg_of(CostBackend("pricey", cost=5.0, prob=0.99))
    router = LadderRouterV2(
        reg, ladders={"categorical": [LadderRung("pricey")]},
        planner=CostAwarePlanner(DynamicRungPlanner(reg), reg))
    with pytest.raises(Abstention):
        router.decide({}, spec(), DecisionPolicy(max_cost=0.01))


# -- router spend feedback ------------------------------------------------------------

def test_router_records_actual_spend():
    reg = reg_of(CostBackend("a", cost=0.2, prob=0.99, actual_cost=0.17))
    ledger = CostLedger(1.0)
    router = LadderRouterV2(registry=reg, rungs=[LadderRung("a", 0.9)],
                            cost_ledger=ledger)
    router.decide({}, spec())
    assert ledger.spent == pytest.approx(0.17)  # actual, not estimate


def test_router_falls_back_to_estimate_without_metadata():
    reg = reg_of(CostBackend("a", cost=0.2, prob=0.99))
    ledger = CostLedger(1.0)
    router = LadderRouterV2(registry=reg, rungs=[LadderRung("a", 0.9)],
                            cost_ledger=ledger)
    router.decide({}, spec())
    assert ledger.spent == pytest.approx(0.2)


def test_no_ledger_no_spend_tracking():
    reg = reg_of(CostBackend("a", cost=0.2, prob=0.99))
    router = LadderRouterV2(registry=reg, rungs=[LadderRung("a", 0.9)])
    router.decide({}, spec())  # must not raise
    assert router.cost_ledger is None
