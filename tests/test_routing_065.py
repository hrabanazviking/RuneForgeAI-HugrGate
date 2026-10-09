"""Slice 065 — hedged inference."""

from __future__ import annotations

import time

import pytest

from hugrgate import (
    Abstention,
    Backend,
    BackendRegistry,
    DecisionPolicy,
    DecisionResult,
    DecisionSpec,
)
from hugrgate.ladder import LadderRung
from hugrgate.routing import HedgedPlanExecutor, LadderRouterV2, RoutingOptions


class HedgeBackend(Backend):
    def __init__(self, name, prob=0.99, sleep_s=0.0):
        self.name = name
        self._prob = prob
        self._sleep = sleep_s
        self.calls = 0

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        self.calls += 1
        if self._sleep:
            time.sleep(self._sleep)
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


def router_for(reg, *names):
    return LadderRouterV2(
        reg, rungs=[LadderRung(n, 0.9) for n in names],
        executor=HedgedPlanExecutor())


def opts(**kw):
    kw.setdefault("strategy", "hedged")
    kw.setdefault("qos", "priority")  # hedging allowed
    kw.setdefault("hedge_delay_ms", 50.0)
    return RoutingOptions(**kw)


def test_hedge_wins_when_primary_slow():
    slow = HedgeBackend("slow", prob=0.99, sleep_s=0.4)
    fast = HedgeBackend("fast", prob=0.99, sleep_s=0.0)
    reg = reg_of(slow, fast)
    t0 = time.perf_counter()
    won = router_for(reg, "slow", "fast").decide(
        {}, spec(), DecisionPolicy(minimum_probability=0.9),
        options=opts())
    elapsed = time.perf_counter() - t0
    assert won.backend == "fast"
    assert won.metadata["execution"] == "hedged"
    assert elapsed < 0.35, f"hedge should beat waiting out 0.4s: {elapsed}"
    assert slow.calls == 1 and fast.calls == 1


def test_no_hedge_when_primary_fast():
    fast = HedgeBackend("fast", prob=0.99, sleep_s=0.0)
    slow = HedgeBackend("slow", prob=0.99, sleep_s=0.4)
    reg = reg_of(fast, slow)
    won = router_for(reg, "fast", "slow").decide(
        {}, spec(), DecisionPolicy(minimum_probability=0.9),
        options=opts(hedge_delay_ms=200.0))
    assert won.backend == "fast"
    assert slow.calls == 0  # hedge never launched


def test_below_gate_hands_off_immediately():
    weak = HedgeBackend("weak", prob=0.5, sleep_s=0.0)
    strong = HedgeBackend("strong", prob=0.99, sleep_s=0.0)
    reg = reg_of(weak, strong)
    t0 = time.perf_counter()
    won = router_for(reg, "weak", "strong").decide(
        {}, spec(), DecisionPolicy(minimum_probability=0.9),
        options=opts(hedge_delay_ms=500.0))
    elapsed = time.perf_counter() - t0
    assert won.backend == "strong"
    assert elapsed < 0.4  # no waiting out the 500ms delay


def test_hedging_disabled_qos_goes_serial():
    slow = HedgeBackend("slow", prob=0.99, sleep_s=0.25)
    fast = HedgeBackend("fast", prob=0.99, sleep_s=0.0)
    reg = reg_of(slow, fast)
    won = router_for(reg, "slow", "fast").decide(
        {}, spec(), DecisionPolicy(minimum_probability=0.9),
        options=opts(qos="best_effort", hedge_delay_ms=50.0))
    assert won.backend == "slow"  # serial: primary wins, no hedge
    assert fast.calls == 0
    assert any("serial climb" in r
               for r in won.metadata["routing_plan"]["rationale"])


def test_all_fail_abstains():
    reg = reg_of(HedgeBackend("a", prob=0.1), HedgeBackend("b", prob=0.2))
    with pytest.raises(Abstention):
        router_for(reg, "a", "b").decide(
            {}, spec(), DecisionPolicy(minimum_probability=0.9),
            options=opts())


def test_hedged_launch_marked_in_audit():
    slow = HedgeBackend("slow", prob=0.99, sleep_s=0.4)
    fast = HedgeBackend("fast", prob=0.99, sleep_s=0.0)
    reg = reg_of(slow, fast)
    won = router_for(reg, "slow", "fast").decide(
        {}, spec(), DecisionPolicy(minimum_probability=0.9),
        options=opts())
    by_name = {e["backend_name"]: e
               for e in won.metadata["ladder_trace"]}
    assert "[hedged]" in by_name["fast"]["detail"]
    assert "[hedged]" not in by_name["slow"]["detail"]
