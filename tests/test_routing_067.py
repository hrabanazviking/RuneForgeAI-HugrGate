"""Slice 067 — fallback graph routing."""

from __future__ import annotations

import pytest

from hugrgate import (
    Abstention,
    Backend,
    BackendError,
    BackendRegistry,
    BackendUnavailable,
    DecisionPolicy,
    DecisionResult,
    DecisionSpec,
    SpecError,
)
from hugrgate.ladder import LadderRung
from hugrgate.routing import (
    FallbackGraph,
    FallbackGraphExecutor,
    LadderRouterV2,
)


class FbBackend(Backend):
    def __init__(self, name, prob=0.95, fail=None):
        self.name = name
        self._prob = prob
        self._fail = fail
        self.calls = 0

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        self.calls += 1
        if self._fail is not None:
            raise self._fail
        n = len(spec.options)
        rest = (1.0 - self._prob) / max(n - 1, 1)
        return DecisionResult(
            value="a", probability=self._prob,
            distribution={o: (self._prob if o == "a" else rest)
                          for o in spec.options},
            backend=self.name)


def reg_of(*bs):
    r = BackendRegistry()
    for b in bs:
        r.register(b)
    return r


def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def router_for(reg, graph, *names):
    return LadderRouterV2(
        reg, rungs=[LadderRung(n, 0.9) for n in names],
        executor=FallbackGraphExecutor(graph))


# -- graph -------------------------------------------------------------------------

def test_self_loop_and_empty_kinds_rejected():
    g = FallbackGraph()
    with pytest.raises(SpecError):
        g.add_edge("a", "a")
    with pytest.raises(SpecError):
        g.add_edge("a", "b", on=())


def test_cycle_detected():
    g = FallbackGraph()
    g.add_edge("a", "b", on=("BackendError",))
    g.add_edge("b", "a", on=("BackendError",))
    with pytest.raises(SpecError) as exc:
        g.validate()
    assert "cycle" in str(exc.value)


def test_fallbacks_specific_before_wildcard():
    g = FallbackGraph()
    g.add_edge("a", "wild", on=("*",))
    g.add_edge("a", "specific", on=("BackendError",))
    assert g.fallbacks("a", "BackendError") == ["specific", "wild"]
    assert g.fallbacks("a", "Other") == ["wild"]
    assert g.fallbacks("b", "BackendError") == []


# -- executor ------------------------------------------------------------------------

def test_error_follows_graph_not_linear_order():
    flaky = FbBackend("flaky", fail=BackendError("boom"))
    linear_next = FbBackend("linear-next", prob=0.99)
    graph_target = FbBackend("graph-target", prob=0.99)
    reg = reg_of(flaky, linear_next, graph_target)
    g = FallbackGraph()
    g.add_edge("flaky", "graph-target", on=("BackendError",))
    won = router_for(reg, g, "flaky", "linear-next").decide(
        {}, spec(), DecisionPolicy(minimum_probability=0.9))
    assert won.backend == "graph-target"
    assert won.metadata["fallback_for"] == "flaky"
    assert linear_next.calls == 0  # graph preempted the linear order


def test_unmatched_error_climbs_linearly():
    flaky = FbBackend("flaky", fail=BackendUnavailable("gone"))
    linear_next = FbBackend("linear-next", prob=0.99)
    reg = reg_of(flaky, linear_next)
    g = FallbackGraph()
    g.add_edge("flaky", "graph-target", on=("BackendError",))  # wrong kind
    won = router_for(reg, g, "flaky", "linear-next").decide(
        {}, spec(), DecisionPolicy(minimum_probability=0.9))
    assert won.backend == "linear-next"


def test_wildcard_edge_matches_any_error():
    flaky = FbBackend("flaky", fail=BackendUnavailable("gone"))
    target = FbBackend("target", prob=0.99)
    reg = reg_of(flaky, target)
    g = FallbackGraph()
    g.add_edge("flaky", "target", on=("*",))
    won = router_for(reg, g, "flaky").decide(
        {}, spec(), DecisionPolicy(minimum_probability=0.9))
    assert won.backend == "target"


def test_runtime_cycle_terminates():
    a = FbBackend("a", fail=BackendError("x"))
    b = FbBackend("b", fail=BackendError("y"))
    reg = reg_of(a, b)
    g = FallbackGraph()
    g.add_edge("a", "b", on=("*",))
    g.add_edge("b", "a", on=("*",))
    # static validate() would reject this; bypass to test runtime guard
    ex = FallbackGraphExecutor(g, validate_graph=False)
    router = LadderRouterV2(reg, rungs=[LadderRung("a", 0.9)],
                            executor=ex)
    with pytest.raises(Abstention):
        router.decide({}, spec(), DecisionPolicy(minimum_probability=0.9))
    assert a.calls == 1 and b.calls == 1  # each attempted exactly once


def test_fallback_inherits_gate():
    flaky = FbBackend("flaky", fail=BackendError("boom"))
    target = FbBackend("target", prob=0.85)  # below the 0.9 gate
    reg = reg_of(flaky, target)
    g = FallbackGraph()
    g.add_edge("flaky", "target", on=("*",))
    with pytest.raises(Abstention):
        router_for(reg, g, "flaky").decide(
            {}, spec(), DecisionPolicy(minimum_probability=0.9))
    # target ran (inherited gate 0.9, its 0.85 fell short) then exhausted
    assert target.calls == 1


def test_executor_validates_graph_by_default():
    g = FallbackGraph()
    g.add_edge("a", "b", on=("*",))
    g.add_edge("b", "a", on=("*",))
    with pytest.raises(SpecError):
        FallbackGraphExecutor(g)
