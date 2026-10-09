"""Slice 059 — memory-aware routing."""

from __future__ import annotations

import pytest

from hugrgate import (Abstention, Backend, BackendRegistry, DecisionPolicy,
                      DecisionResult, DecisionSpec)
from hugrgate.ladder import LadderRung
from hugrgate.routing import (DEFAULT_LOCAL_MEMORY_MB,
                              DEFAULT_REMOTE_MEMORY_MB, DynamicRungPlanner,
                              LadderRouterV2, MemoryAwarePlanner, MemoryModel,
                              RouterContext, RoutingOptions)


class MemBackend(Backend):
    def __init__(self, name, memory_mb=None, prob=0.95, remote=False):
        self.name = name
        self._memory_mb = memory_mb
        self._prob = prob
        self.is_remote = remote
        if memory_mb == "method":
            self.estimated_memory_mb = lambda: 1234.0

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

    def hardware_requirements(self):
        if isinstance(self._memory_mb, (int, float)):
            return {"memory_mb": self._memory_mb}
        return {}


def reg_of(*bs):
    r = BackendRegistry()
    for b in bs:
        r.register(b)
    return r


def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def ctx(options=None):
    return RouterContext.from_request({}, spec(), DecisionPolicy(),
                                      options or RoutingOptions())


# -- model -----------------------------------------------------------------------

def test_model_resolution_order():
    model = MemoryModel()
    declared = MemBackend("d", memory_mb=2048.0)
    assert model.estimate_mb(declared) == 2048.0
    via_method = MemBackend("m", memory_mb="method")
    assert model.estimate_mb(via_method) == 1234.0
    local = MemBackend("l")
    assert model.estimate_mb(local) == DEFAULT_LOCAL_MEMORY_MB
    remote = MemBackend("r", remote=True)
    assert model.estimate_mb(remote) == DEFAULT_REMOTE_MEMORY_MB
    with pytest.raises(ValueError):
        MemoryModel(local_mb=-1)


# -- planner -----------------------------------------------------------------------

def test_planner_prunes_over_budget_rungs():
    reg = reg_of(MemBackend("huge", memory_mb=8192.0),
                 MemBackend("tiny", memory_mb=256.0))
    planner = MemoryAwarePlanner(DynamicRungPlanner(reg), reg,
                                 budget_mb=1024.0)
    plan = planner.plan(ctx())
    assert [n.backend_name for n in plan.nodes] == ["tiny"]
    assert plan.nodes[0].params["memory_estimate_mb"] == 256.0
    assert any("pruned 1" in r for r in plan.rationale)


def test_boundary_equal_to_budget_survives():
    reg = reg_of(MemBackend("exact", memory_mb=1024.0))
    planner = MemoryAwarePlanner(DynamicRungPlanner(reg), reg,
                                 budget_mb=1024.0)
    assert [n.backend_name for n in planner.plan(ctx()).nodes] == ["exact"]


def test_no_budget_annotates_only():
    reg = reg_of(MemBackend("a", memory_mb=99999.0))
    planner = MemoryAwarePlanner(DynamicRungPlanner(reg), reg)
    plan = planner.plan(ctx())
    assert [n.backend_name for n in plan.nodes] == ["a"]
    assert plan.nodes[0].params["memory_estimate_mb"] == 99999.0


def test_options_budget_used_when_no_explicit():
    reg = reg_of(MemBackend("huge", memory_mb=8192.0))
    planner = MemoryAwarePlanner(DynamicRungPlanner(reg), reg)
    plan = planner.plan(ctx(RoutingOptions(max_memory_mb=512.0)))
    assert plan.nodes == []
    with pytest.raises(ValueError):
        MemoryAwarePlanner(DynamicRungPlanner(reg), reg, budget_mb=-5.0)


def test_empty_memory_plan_abstains_end_to_end():
    reg = reg_of(MemBackend("huge", memory_mb=8192.0, prob=0.99))
    router = LadderRouterV2(
        reg, ladders={"categorical": [LadderRung("huge")]},
        planner=MemoryAwarePlanner(DynamicRungPlanner(reg), reg,
                                   budget_mb=512.0))
    with pytest.raises(Abstention):
        router.decide({}, spec())


def test_fitting_rung_wins_end_to_end():
    reg = reg_of(MemBackend("huge", memory_mb=8192.0, prob=0.99),
                 MemBackend("tiny", memory_mb=256.0, prob=0.95))
    router = LadderRouterV2(
        reg, ladders={"categorical": [LadderRung("huge")]},
        planner=MemoryAwarePlanner(DynamicRungPlanner(reg), reg,
                                   budget_mb=512.0))
    won = router.decide({}, spec(), DecisionPolicy(minimum_probability=0.9))
    assert won.backend == "tiny"
