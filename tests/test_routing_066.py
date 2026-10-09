"""Slice 066 — early-exit routing."""

from __future__ import annotations

import pytest

from hugrgate import (Abstention, Backend, BackendRegistry, DecisionPolicy,
                      DecisionResult, DecisionSpec)
from hugrgate.ladder import LadderRung
from hugrgate.provenance import ProvenanceStore
from hugrgate.routing import (EarlyExitExecutor, LadderRouterV2,
                              RoutingOptions)


class ExitBackend(Backend):
    def __init__(self, name, prob=0.9):
        self.name = name
        self._prob = prob
        self.calls = 0

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        self.calls += 1
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


def router_for(reg, *names, gate=0.99, **kw):
    return LadderRouterV2(
        reg, rungs=[LadderRung(n, gate) for n in names],
        executor=EarlyExitExecutor(), **kw)


def test_fast_path_accepts_below_strict_rung_gate():
    a = ExitBackend("a", prob=0.98)
    b = ExitBackend("b", prob=0.99)
    reg = reg_of(a, b)
    won = router_for(reg, "a", "b").decide(
        {}, spec(), DecisionPolicy(),
        options=RoutingOptions(fast_path_probability=0.97,
                               early_exit_delta=0.0))
    assert won.backend == "a"
    assert won.metadata["early_exit"] == "fast_path"
    assert b.calls == 0  # never even attempted
    assert "fast-path bar" in won.metadata["ladder_trace"][0]["detail"]


def test_normal_gate_clear_has_no_early_exit_marker():
    a = ExitBackend("a", prob=0.985)
    reg = reg_of(a)
    won = router_for(reg, "a", gate=0.98).decide(
        {}, spec(), DecisionPolicy(),
        options=RoutingOptions(qos="critical",  # bar 0.99 > 0.985
                               fast_path_probability=0.999,
                               early_exit_delta=0.0))
    assert won.backend == "a"
    assert "early_exit" not in won.metadata
    assert won.metadata["execution"] == "early_exit"


def test_diminishing_returns_accepts_best():
    # gate 0.99 everywhere; probs stagnate: 0.85 -> 0.86 -> 0.86
    rungs = [ExitBackend(f"r{i}", prob=p)
             for i, p in enumerate([0.85, 0.86, 0.86, 0.861])]
    reg = reg_of(*rungs)
    won = router_for(reg, *[b.name for b in rungs]).decide(
        {}, spec(), DecisionPolicy(minimum_probability=0.8),
        options=RoutingOptions(fast_path_probability=0.999,
                               early_exit_delta=0.05))
    assert won.metadata["early_exit"] == "diminishing_returns"
    # exits after 3 stagnant attempts; the 0.861 rung is never attempted
    assert won.probability == pytest.approx(0.86)
    assert rungs[2].calls == 1
    assert rungs[3].calls == 0
    by_idx = {e["rung_index"]: e["outcome"]
              for e in won.metadata["ladder_trace"]}
    assert by_idx[1] == "accepted"  # best rung's entry marked accepted


def test_diminishing_returns_stops_early_not_at_end():
    rungs = [ExitBackend(f"r{i}", prob=0.85) for i in range(6)]
    reg = reg_of(*rungs)
    won = router_for(reg, *[b.name for b in rungs]).decide(
        {}, spec(), DecisionPolicy(minimum_probability=0.8),
        options=RoutingOptions(fast_path_probability=0.999,
                               early_exit_delta=0.05))
    assert won.metadata["early_exit"] == "diminishing_returns"
    # stagnant from the start: exits after 3 attempts, rungs 3-5 untouched
    assert rungs[2].calls == 1
    assert rungs[3].calls == 0
    assert rungs[5].calls == 0


def test_no_improvement_below_policy_min_abstains_early():
    rungs = [ExitBackend(f"r{i}", prob=0.5) for i in range(6)]
    reg = reg_of(*rungs)
    with pytest.raises(Abstention) as exc:
        router_for(reg, *[b.name for b in rungs]).decide(
            {}, spec(), DecisionPolicy(minimum_probability=0.8),
            options=RoutingOptions(fast_path_probability=0.999,
                                   early_exit_delta=0.05))
    assert exc.value.reason == "early_exit_no_improvement"
    assert rungs[3].calls == 0  # stopped after 3, not 6


def test_improving_climb_runs_to_end():
    rungs = [ExitBackend(f"r{i}", prob=p)
             for i, p in enumerate([0.5, 0.6, 0.7, 0.8])]
    reg = reg_of(*rungs)
    won = router_for(reg, *[b.name for b in rungs], gate=0.75).decide(
        {}, spec(), DecisionPolicy(minimum_probability=0.75),
        options=RoutingOptions(fast_path_probability=0.999,
                               early_exit_delta=0.05))
    # steady 0.1 gains: no stagnation, normal gate clear at the end
    assert won.probability == pytest.approx(0.8)
    assert "early_exit" not in won.metadata
    assert all(b.calls == 1 for b in rungs)


def test_single_provenance_record_per_attempt():
    store = ProvenanceStore()
    rungs = [ExitBackend(f"r{i}", prob=0.85) for i in range(4)]
    reg = reg_of(*rungs)
    router_for(reg, *[b.name for b in rungs], provenance=store).decide(
        {}, spec(), DecisionPolicy(minimum_probability=0.8),
        options=RoutingOptions(fast_path_probability=0.999,
                               early_exit_delta=0.05))
    assert store.count() == 3  # 3 attempts, no double-logging
