"""Slice 064 — parallel speculative rungs."""

from __future__ import annotations

import time

import pytest

from hugrgate import (Abstention, Backend, BackendRegistry, BackendError,
                      DecisionPolicy, DecisionResult, DecisionSpec)
from hugrgate.ladder import LadderRung
from hugrgate.routing import (LadderRouterV2, ParallelPlanExecutor,
                              RouterContext, RoutingOptions, RungMode)


class RaceBackend(Backend):
    def __init__(self, name, prob=0.95, sleep_s=0.0, fail=None):
        self.name = name
        self._prob = prob
        self._sleep = sleep_s
        self._fail = fail
        self.calls = 0

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        self.calls += 1
        if self._sleep:
            time.sleep(self._sleep)
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


def router_for(reg, *names, executor=None, **kw):
    return LadderRouterV2(
        reg, rungs=[LadderRung(n, 0.9) for n in names],
        executor=executor or ParallelPlanExecutor(), **kw)


def opts(**kw):
    kw.setdefault("strategy", "parallel")
    kw.setdefault("qos", "priority")  # width 3, allows fan-out
    return RoutingOptions(**kw)


# -- behavior ------------------------------------------------------------------------

def test_first_gate_clear_wins_not_first_rung():
    slow = RaceBackend("slow", prob=0.99, sleep_s=0.3)
    fast = RaceBackend("fast", prob=0.99, sleep_s=0.0)
    reg = reg_of(slow, fast)
    won = router_for(reg, "slow", "fast").decide(
        {}, spec(), DecisionPolicy(minimum_probability=0.9),
        options=opts())
    assert won.backend == "fast"
    assert won.metadata["execution"] == "parallel_speculative"


def test_weak_fast_loses_to_strong_slow():
    fast_weak = RaceBackend("fast-weak", prob=0.5, sleep_s=0.0)
    slow_strong = RaceBackend("slow-strong", prob=0.99, sleep_s=0.2)
    reg = reg_of(fast_weak, slow_strong)
    won = router_for(reg, "fast-weak", "slow-strong").decide(
        {}, spec(), DecisionPolicy(minimum_probability=0.9),
        options=opts())
    assert won.backend == "slow-strong"
    trace = won.metadata["ladder_trace"]
    by_name = {e["backend_name"]: e["outcome"] for e in trace}
    assert by_name["fast-weak"] == "below_confidence"
    assert by_name["slow-strong"] == "accepted"


def test_all_below_gate_abstains_with_full_trace():
    reg = reg_of(RaceBackend("a", prob=0.1), RaceBackend("b", prob=0.2))
    with pytest.raises(Abstention) as exc:
        router_for(reg, "a", "b").decide(
            {}, spec(), DecisionPolicy(minimum_probability=0.9),
            options=opts())
    assert exc.value.reason == "ladder_exhausted"
    assert len(exc.value.details["ladder_trace"]) == 2


def test_failing_backend_does_not_kill_wave():
    dead = RaceBackend("dead", fail=BackendError("boom"))
    alive = RaceBackend("alive", prob=0.99, sleep_s=0.1)
    reg = reg_of(dead, alive)
    won = router_for(reg, "dead", "alive").decide(
        {}, spec(), DecisionPolicy(minimum_probability=0.9),
        options=opts())
    assert won.backend == "alive"
    by_name = {e["backend_name"]: e["outcome"]
               for e in won.metadata["ladder_trace"]}
    assert by_name["dead"] == "backend_error"


def test_width_cap_serializes_waves():
    # width 1 -> strictly serial order: first rung wins ties
    a = RaceBackend("a", prob=0.99, sleep_s=0.0)
    b = RaceBackend("b", prob=0.99, sleep_s=0.0)
    reg = reg_of(a, b)
    won = router_for(reg, "a", "b").decide(
        {}, spec(), DecisionPolicy(minimum_probability=0.9),
        options=opts(parallel_width=1))
    assert won.backend == "a"


def test_best_effort_qos_never_fans_out():
    a = RaceBackend("a", prob=0.99, sleep_s=0.2)
    b = RaceBackend("b", prob=0.99, sleep_s=0.0)
    reg = reg_of(a, b)
    t0 = time.perf_counter()
    won = router_for(reg, "a", "b").decide(
        {}, spec(), DecisionPolicy(minimum_probability=0.9),
        options=opts(qos="best_effort", parallel_width=4))
    elapsed = time.perf_counter() - t0
    # width min(4, 1) = 1: serial waves, a (0.2s) then b; a wins first wave
    assert won.backend == "a"
    assert elapsed >= 0.15


def test_unknown_backend_skipped_in_parallel():
    reg = reg_of(RaceBackend("real", prob=0.99))
    won = router_for(reg, "ghost", "real").decide(
        {}, spec(), DecisionPolicy(minimum_probability=0.9),
        options=opts())
    assert won.backend == "real"
    by_name = {e["backend_name"]: e["outcome"]
               for e in won.metadata["ladder_trace"]}
    assert by_name["ghost"] == "skipped_unknown_backend"


def test_plan_metadata_and_provenance():
    from hugrgate.provenance import ProvenanceStore
    store = ProvenanceStore()
    reg = reg_of(RaceBackend("a", prob=0.99))
    r = router_for(reg, "a", provenance=store)
    won = r.decide({}, spec(), DecisionPolicy(minimum_probability=0.9),
                   options=opts())
    assert won.metadata["routing_plan"]["fingerprint"] == \
        r.last_plan.fingerprint
    assert store.count() >= 1
