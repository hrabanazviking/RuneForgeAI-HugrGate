"""Slice 052 — dynamic rung construction."""

from __future__ import annotations

import pytest

from hugrgate import (
    Abstention,
    Backend,
    BackendRegistry,
    DecisionPolicy,
    DecisionResult,
    DecisionSpec,
)
from hugrgate.routing import (
    DynamicRungPlanner,
    LadderRouterV2,
    RouterContext,
    RungBuilder,
)


class DynBackend(Backend):
    def __init__(self, name, prob=0.9, cost=0.0, latency=5.0, remote=False,
                 spec_types=("categorical",)):
        self.name = name
        self._prob = prob
        self._cost = cost
        self._latency = latency
        self.is_remote = remote
        self._spec_types = tuple(spec_types)

    def capabilities(self):
        return {"spec_types": list(self._spec_types)}

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


def registry_of(*backends):
    r = BackendRegistry()
    for b in backends:
        r.register(b)
    return r


def ctx_for(policy=None, spec=None):
    return RouterContext.from_request(
        {}, spec or DecisionSpec(type="categorical", options=["a", "b"]),
        policy or DecisionPolicy())


# -- builder basics ------------------------------------------------------------

def test_builds_rungs_cheapest_first():
    reg = registry_of(DynBackend("expensive", cost=0.5, latency=5.0),
                      DynBackend("cheap", cost=0.01, latency=50.0))
    nodes = RungBuilder().build(reg, ctx_for())
    assert [n.backend_name for n in nodes] == ["cheap", "expensive"]
    assert all("dynamic rung" in n.why for n in nodes)


def test_latency_ordering():
    reg = registry_of(DynBackend("slow", cost=0.0, latency=500.0),
                      DynBackend("fast", cost=0.0, latency=5.0))
    nodes = RungBuilder(order="latency").build(reg, ctx_for())
    assert [n.backend_name for n in nodes] == ["fast", "slow"]


def test_preferred_backends_float_first():
    reg = registry_of(DynBackend("a", cost=0.01), DynBackend("b", cost=0.0))
    policy = DecisionPolicy(preferred_backends=["a"])
    nodes = RungBuilder().build(reg, ctx_for(policy))
    assert [n.backend_name for n in nodes] == ["a", "b"]


def test_allowlist_and_unsupported_pruned():
    reg = registry_of(
        DynBackend("ok", spec_types=("categorical",)),
        DynBackend("wrong-type", spec_types=("ranking",)),
        DynBackend("blocked", spec_types=("categorical",)))
    policy = DecisionPolicy(allowed_backends=["ok", "wrong-type"])
    nodes = RungBuilder().build(reg, ctx_for(policy))
    assert [n.backend_name for n in nodes] == ["ok"]


def test_remote_prefiltered_when_policy_forbids():
    reg = registry_of(DynBackend("local"), DynBackend("cloud", remote=True))
    nodes = RungBuilder().build(
        reg, ctx_for(DecisionPolicy(remote_inference=False)))
    assert [n.backend_name for n in nodes] == ["local"]
    nodes = RungBuilder().build(
        reg, ctx_for(DecisionPolicy(remote_inference=True)))
    assert [n.backend_name for n in nodes] == ["local", "cloud"]


def test_max_rungs_cap_and_empty_registry():
    reg = registry_of(DynBackend("a"), DynBackend("b"), DynBackend("c"))
    nodes = RungBuilder(max_rungs=2).build(reg, ctx_for())
    assert len(nodes) == 2
    assert RungBuilder().build(BackendRegistry(), ctx_for()) == []
    with pytest.raises(ValueError):
        RungBuilder(order="teleport")
    with pytest.raises(ValueError):
        RungBuilder(max_rungs=-1)


def test_extra_filter_plugs_in():
    reg = registry_of(DynBackend("a"), DynBackend("b"))
    builder = RungBuilder(
        extra_filters=[lambda b, ctx: b.name != "b"])
    nodes = builder.build(reg, ctx_for())
    assert [n.backend_name for n in nodes] == ["a"]


def test_builder_inherits_policy_gate_and_latency_budget():
    reg = registry_of(DynBackend("a"))
    policy = DecisionPolicy(minimum_probability=0.75,
                            maximum_latency_ms=250.0)
    nodes = RungBuilder().build(reg, ctx_for(policy))
    assert nodes[0].min_confidence == 0.75
    assert nodes[0].latency_budget_ms == 250.0


# -- planner + router integration ----------------------------------------------

def test_dynamic_planner_end_to_end():
    from hugrgate.ladder import LadderRung
    reg = registry_of(DynBackend("weak", prob=0.4, cost=0.0),
                      DynBackend("strong", prob=0.99, cost=0.1))
    # v1 ctor still requires *some* configured ladder; the dynamic planner
    # ignores it and rebuilds per request.
    router = LadderRouterV2(
        reg, ladders={"categorical": [LadderRung("weak")]},
        planner=DynamicRungPlanner(reg))
    result = router.decide({}, DecisionSpec(type="categorical",
                                            options=["a", "b"]),
                           DecisionPolicy(minimum_probability=0.8))
    assert result.backend == "strong"
    assert result.probability == 0.99
    assert router.last_plan.created_by == "DynamicRungPlanner"
    # dynamic plan ignores the configured rung and orders by cost
    assert [n.backend_name for n in router.last_plan.nodes] == [
        "weak", "strong"]


def test_empty_dynamic_plan_abstains():
    reg = registry_of(DynBackend("cloud", remote=True))
    router = LadderRouterV2(
        reg, rungs=[__import__("hugrgate.ladder", fromlist=["LadderRung"])
                    .LadderRung("cloud")],
        planner=DynamicRungPlanner(reg))
    with pytest.raises(Abstention):
        router.decide({}, DecisionSpec(type="categorical", options=["a", "b"]),
                      DecisionPolicy(remote_inference=False))
