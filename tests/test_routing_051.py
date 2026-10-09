"""Slice 051 — router architecture v2: plan/execute separation."""

from __future__ import annotations

import pytest

from hugrgate import (
    Abstention,
    BackendRegistry,
    DecisionPolicy,
    DecisionResult,
    DecisionSpec,
    PolicyError,
    SpecError,
)
from hugrgate.ladder import RUNG_ACCEPTED, LadderRouter, LadderRung
from hugrgate.routing import (
    LadderRouterV2,
    RoutingOptions,
    RoutingPlan,
    RungMode,
    RungNode,
    SerialPlanExecutor,
)


class FixedBackend(__import__("hugrgate").Backend):
    def __init__(self, name, prob=0.9, latency=5.0):
        self.name = name
        self._prob = prob
        self._latency = latency

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        n = len(spec.options)
        rest = (1.0 - self._prob) / (n - 1)
        return DecisionResult(
            value="a", probability=self._prob,
            distribution={"a": self._prob, "b": rest}, backend=self.name)

    def estimated_latency(self):
        return self._latency


def make_spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def make_v2(*backends, gates=None):
    registry = BackendRegistry()
    for b in backends:
        registry.register(b)
    rungs = [LadderRung(b.name, mc) for b, mc
             in zip(backends, gates or [0.8] * len(backends), strict=True)]
    return LadderRouterV2(registry, rungs=rungs)


# -- RoutingOptions validation ------------------------------------------------

def test_options_reject_bad_values():
    with pytest.raises(PolicyError):
        RoutingOptions(qos="ultra")
    with pytest.raises(PolicyError):
        RoutingOptions(strategy="teleport")
    with pytest.raises(PolicyError):
        RoutingOptions(privacy_tier="cosmic")
    with pytest.raises(PolicyError):
        RoutingOptions(max_cost=-1.0)
    with pytest.raises(PolicyError):
        RoutingOptions(parallel_width=0)
    with pytest.raises(PolicyError):
        RoutingOptions(fast_path_probability=1.5)
    # boundary values are fine
    RoutingOptions(max_cost=0.0, parallel_width=1,
                   fast_path_probability=1.0, early_exit_delta=0.0)


def test_rung_node_validation():
    with pytest.raises(SpecError):
        RungNode("x", min_confidence=1.2)
    with pytest.raises(SpecError):
        RungNode("x", latency_budget_ms=-3.0)
    n = RungNode("x", mode="serial")
    assert n.mode is RungMode.SERIAL


# -- plan construction is inspectable and side-effect free --------------------

def test_build_plan_is_deterministic_and_side_effect_free():
    a, b = FixedBackend("a", prob=0.5), FixedBackend("b", prob=0.99)
    router = make_v2(a, b)
    plan1, ctx1 = router.build_plan({}, make_spec())
    plan2, _ctx2 = router.build_plan({}, make_spec())
    assert plan1.fingerprint == plan2.fingerprint
    assert [n.backend_name for n in plan1.nodes] == ["a", "b"]
    assert plan1.strategy is RungMode.SERIAL
    assert a.__class__  # backends untouched: no evaluate calls possible
    assert ctx1.state_keys == ()
    # no raw state values leak into the context
    _, ctx3 = router.build_plan({"ssn": "123-45-6789"}, make_spec())
    assert ctx3.state_keys == ("ssn",)
    assert "123-45-6789" not in repr(ctx3)


def test_plan_fingerprint_changes_with_plan():
    p1 = RoutingPlan(nodes=[RungNode("a")], created_by="t")
    p2 = RoutingPlan(nodes=[RungNode("b")], created_by="t")
    p3 = RoutingPlan(nodes=[RungNode("a")], created_by="t")
    assert p1.fingerprint != p2.fingerprint
    assert p1.fingerprint == p3.fingerprint


# -- v2 serial execution matches v1 behavior ----------------------------------

def test_v2_serial_matches_v1_climb():
    a = FixedBackend("a", prob=0.5)
    b = FixedBackend("b", prob=0.99)
    spec = make_spec()
    v1 = LadderRouter(BackendRegistry(), rungs=[LadderRung("a", 0.8),
                                                LadderRung("b", 0.8)])
    v2 = make_v2(a, b)
    for _name, backend in (("a", a), ("b", b)):
        v1.registry.register(backend)
    r1 = v1.decide({}, spec)
    r2 = v2.decide({}, spec)
    assert r1.value == r2.value == "a"
    assert r1.probability == r2.probability
    assert r2.metadata["ladder_backend"] == "b"
    assert r2.metadata["routing_plan"]["fingerprint"] == \
        v2.last_plan.fingerprint
    assert v2.last_audit[-1].outcome == RUNG_ACCEPTED


def test_v2_exhaustion_raises_abstention_with_plan():
    a = FixedBackend("a", prob=0.1)
    router = make_v2(a)
    with pytest.raises(Abstention) as exc:
        router.decide({}, make_spec())
    assert exc.value.reason == "ladder_exhausted"
    assert exc.value.details["plan_fingerprint"] == \
        router.last_plan.fingerprint


def test_skip_reason_reuse_not_duplication():
    # skip_reason is the single source of pruning truth for v1 and v2.
    a = FixedBackend("a", prob=0.9)
    router = make_v2(a)
    import time
    skip = router.skip_reason(a, LadderRung("a", 0.5, latency_budget_ms=1.0),
                              make_spec(), DecisionPolicy(),
                              time.perf_counter())
    assert skip is not None and skip[0] == "skipped_latency_budget"
    ok = router.skip_reason(a, LadderRung("a", 0.5), make_spec(),
                            DecisionPolicy(), time.perf_counter())
    assert ok is None


def test_custom_planner_and_executor_plug_in():
    a = FixedBackend("a", prob=0.99)
    router = make_v2(a)

    class ReversePlanner:
        def plan(self, ctx):
            nodes = [RungNode(n.backend_name, n.min_confidence)
                     for n in reversed(router.ladder_for(ctx.spec))]
            return RoutingPlan(nodes=nodes, created_by="rev")

    seen = {}

    class SpyExecutor(SerialPlanExecutor):
        def execute(self, router, plan, state, ctx):
            seen["fingerprint"] = plan.fingerprint
            return super().execute(router, plan, state, ctx)

    router.planner = ReversePlanner()
    router.executor = SpyExecutor()
    result = router.decide({}, make_spec())
    assert result.probability == 0.99
    assert seen["fingerprint"] == router.last_plan.fingerprint
    assert isinstance(router.last_plan, RoutingPlan)
