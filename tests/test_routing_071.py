"""Slice 071 — route simulation."""

from __future__ import annotations

import pytest

from hugrgate import (Abstention, Backend, BackendRegistry, DecisionPolicy,
                      DecisionResult, DecisionSpec)
from hugrgate.ladder import LadderRung
from hugrgate.routing import (LadderRouterV2, RouterContext, RoutingOptions,
                              SimulationReport, simulate)


class SimBackend(Backend):
    def __init__(self, name, latency=10.0, cost=0.05, prob=0.9,
                 remote=False, explode=True):
        self.name = name
        self._latency = latency
        self._cost = cost
        self._prob = prob
        self.is_remote = remote
        self._explode = explode
        self.calls = 0

    def capabilities(self):
        return {"spec_types": ["categorical"], "accuracy": 0.9}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        self.calls += 1
        if self._explode:
            raise AssertionError("simulation must never call backends")
        n = len(spec.options)
        rest = (1.0 - self._prob) / max(n - 1, 1)
        from hugrgate import DecisionResult
        return DecisionResult(
            value="a", probability=self._prob,
            distribution={o: (self._prob if o == "a" else rest)
                          for o in spec.options},
            backend=self.name)

    def estimated_latency(self):
        return self._latency

    def estimated_cost(self):
        return self._cost

    def hardware_requirements(self):
        return {"power_watts": 20.0, "memory_mb": 256.0}


def reg_of(*bs):
    r = BackendRegistry()
    for b in bs:
        r.register(b)
    return r


def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def test_simulation_predicts_skips_and_totals():
    reg = reg_of(SimBackend("ok", latency=10.0, cost=0.05),
                 SimBackend("slow", latency=500.0, cost=0.01),
                 SimBackend("cloud", latency=10.0, remote=True))
    router = LadderRouterV2(
        reg, rungs=[LadderRung("ghost", 0.5),
                    LadderRung("ok", 0.5),
                    LadderRung("slow", 0.5, latency_budget_ms=100.0),
                    LadderRung("cloud", 0.5)])
    plan, ctx = router.build_plan(
        {}, spec(), DecisionPolicy(remote_inference=False))
    report = simulate(router, plan, {}, ctx)
    assert isinstance(report, SimulationReport)
    assert report.plan_fingerprint == plan.fingerprint
    by_name = {r.backend_name: r for r in report.rungs}
    assert by_name["ghost"].would_skip
    assert "not in registry" in by_name["ghost"].skip_reason
    assert by_name["slow"].would_skip
    assert "latency" in by_name["slow"].skip_reason
    assert by_name["cloud"].would_skip  # remote blocked
    assert not by_name["ok"].would_skip
    assert by_name["ok"].est_latency_ms == 10.0
    assert by_name["ok"].est_cost == pytest.approx(0.05)
    assert by_name["ok"].est_energy_j == pytest.approx(0.01 * 20.0)
    assert by_name["ok"].est_memory_mb == 256.0
    assert 0.0 < by_name["ok"].capability <= 1.0
    totals = report.totals()
    assert totals["runnable_rungs"] == 1
    assert totals["skipped_rungs"] == 3
    assert totals["est_total_latency_ms"] == 10.0
    assert "cannot predict which rung" in report.note


def test_what_if_table_cumulative():
    reg = reg_of(SimBackend("a", latency=10.0, cost=0.1),
                 SimBackend("b", latency=20.0, cost=0.2),
                 SimBackend("c", latency=30.0, cost=0.3))
    router = LadderRouterV2(
        reg, rungs=[LadderRung("a", 0.5), LadderRung("b", 0.5),
                    LadderRung("c", 0.5)])
    plan, ctx = router.build_plan({}, spec())
    report = simulate(router, plan, {}, ctx)
    table = report.what_if_win
    assert [row["if_rung_wins"] for row in table] == [0, 1, 2]
    assert table[0]["cumulative_latency_ms"] == 10.0
    assert table[1]["cumulative_latency_ms"] == 30.0
    assert table[2]["cumulative_latency_ms"] == 60.0
    assert table[2]["cumulative_cost"] == pytest.approx(0.6)
    assert table[2]["cumulative_energy_j"] == pytest.approx(0.06 * 20.0)


def test_simulation_never_calls_backends():
    backends = [SimBackend(f"b{i}") for i in range(3)]
    reg = reg_of(*backends)
    router = LadderRouterV2(
        reg, rungs=[LadderRung(b.name, 0.5) for b in backends])
    plan, ctx = router.build_plan({}, spec())
    simulate(router, plan, {}, ctx)
    assert all(b.calls == 0 for b in backends)


def test_empty_plan_simulation():
    from hugrgate.routing import RoutingPlan
    reg = reg_of(SimBackend("a"))
    router = LadderRouterV2(reg, rungs=[LadderRung("a", 0.5)])
    plan = RoutingPlan(nodes=[], created_by="test")
    ctx = RouterContext.from_request({}, spec())
    report = simulate(router, plan, {}, ctx)
    assert report.totals()["runnable_rungs"] == 0
    assert report.what_if_win == []
    assert report.to_dict()["plan_fingerprint"] == plan.fingerprint


def test_simulation_matches_execution_skips():
    # The same plan executed for real must skip exactly the rungs the
    # simulation predicted skipped.
    reg = reg_of(SimBackend("ok", latency=10.0, prob=0.1, explode=False),
                 SimBackend("slow", latency=500.0, explode=False))
    router = LadderRouterV2(
        reg, rungs=[LadderRung("ok", 0.5),
                    LadderRung("slow", 0.5, latency_budget_ms=100.0)])
    plan, ctx = router.build_plan({}, spec())
    report = simulate(router, plan, {}, ctx)
    predicted_skipped = {r.backend_name for r in report.rungs
                         if r.would_skip}
    # "ok" falls below gate, "slow" is reached and latency-skipped
    with pytest.raises(Abstention):
        router.decide({}, spec())
    actual_skipped = {e.backend_name for e in router.last_audit
                      if e.outcome == "skipped_latency_budget"}
    assert predicted_skipped == actual_skipped == {"slow"}
