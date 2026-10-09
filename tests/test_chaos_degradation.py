"""Slice 270 — degradation plans tests."""

from __future__ import annotations

import json

import pytest

from hugrgate.cache import DecisionCache
from hugrgate.chaos import (
    DegradationPlan,
    DegradationPlanRegistry,
    DegradationReport,
    DegradationStep,
    builtin_degradation_plans,
)
from hugrgate.core import HugrGate
from hugrgate.errors import BackendUnavailable, SpecError
from hugrgate.fallback import FallbackChain
from hugrgate.policy import DecisionPolicy
from hugrgate.spec import DecisionSpec
from tests.conftest import StubBackend


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def _step(name="s", run=None):
    return DegradationStep(name=name, description=f"step {name}",
                           run=run or (lambda ctx: f"did {name}"))


def _plan(name="p", triggers=("backend_unavailable",), steps=None):
    return DegradationPlan(
        name=name, description=f"plan {name}", triggers=triggers,
        steps=tuple(steps or [_step()]))


# --- registry mechanics ----------------------------------------------------------------------------------------

def test_register_get_names_match():
    reg = DegradationPlanRegistry()
    reg.register(_plan("a", triggers=("x",)))
    reg.register(_plan("b", triggers=("x", "y")))
    assert reg.names() == ["a", "b"]
    assert reg.get("a").description == "plan a"
    assert [p.name for p in reg.plans_for("y")] == ["b"]
    assert [p.name for p in reg.plans_for("x")] == ["a", "b"]
    assert reg.plans_for("zzz") == []
    with pytest.raises(SpecError, match="unknown"):
        reg.get("nope")
    with pytest.raises(SpecError, match="duplicate"):
        reg.register(_plan("a"))
    with pytest.raises(SpecError, match="can only register"):
        reg.register("nope")  # type: ignore[arg-type]


def test_plan_validation():
    with pytest.raises(SpecError, match="non-empty"):
        DegradationPlan("", "d", triggers=("x",), steps=(_step(),))
    with pytest.raises(SpecError, match="trigger"):
        DegradationPlan("p", "d", triggers=(), steps=(_step(),))
    with pytest.raises(SpecError, match="at least one"):
        DegradationPlan("p", "d", triggers=("x",), steps=())
    with pytest.raises(SpecError, match="duplicate step"):
        DegradationPlan("p", "d", triggers=("x",),
                        steps=(_step("s"), _step("s")))
    with pytest.raises(SpecError, match="non-empty"):
        DegradationStep("", "d", lambda ctx: "x")
    with pytest.raises(SpecError, match="callable"):
        DegradationStep("s", "d", "not-callable")  # type: ignore[arg-type]


def test_execute_runs_all_steps_and_continues_past_failure():
    order = []
    reg = DegradationPlanRegistry()
    reg.register(DegradationPlan(
        name="p", description="d", triggers=("x",),
        steps=(_step("one", lambda ctx: order.append("one") or "ok-1"),
               _step("two", lambda ctx: (_ for _ in ()).throw(
                   RuntimeError("step blew up"))),
               _step("three", lambda ctx: order.append("three") or "ok-3"))))
    report = reg.execute("p", failure_code="x")
    assert isinstance(report, DegradationReport)
    assert order == ["one", "three"]  # continued past the failure
    assert [s.status for s in report.steps] == ["applied", "failed",
                                                "applied"]
    assert "step blew up" in report.steps[1].note
    assert report.outcome == "partial"
    assert report.degraded_gracefully is True
    json.dumps(report.to_dict())


def test_execute_skip_and_empty_outcome():
    reg = DegradationPlanRegistry()
    reg.register(DegradationPlan(
        name="p", description="d", triggers=("x",),
        steps=(_step("s1", lambda ctx: "SKIP: not applicable"),
               _step("s2", lambda ctx: (_ for _ in ()).throw(
                   ValueError("nope"))))))
    report = reg.execute("p")
    assert [s.status for s in report.steps] == ["skipped", "failed"]
    assert report.steps[0].note == "not applicable"
    assert report.outcome == "none"
    assert report.degraded_gracefully is False


def test_execute_unknown_plan():
    with pytest.raises(SpecError, match="unknown"):
        DegradationPlanRegistry().execute("ghost")


# --- builtin plans -----------------------------------------------------------------------------------------------

def test_builtin_registry_has_both_plans():
    reg = builtin_degradation_plans()
    assert reg.names() == ["failover-then-abstain", "serve-stale-cache"]
    assert {p.name for p in reg.plans_for("backend_unavailable")} == {
        "failover-then-abstain", "serve-stale-cache"}
    assert [p.name for p in reg.plans_for("bulkhead_rejected")] == [
        "failover-then-abstain"]
    assert reg.plans_for("spec_error") == []


def test_serve_stale_cache_with_real_cache_hit():
    gate = HugrGate()
    gate.register(StubBackend(name="primary", value="a"))
    cache = DecisionCache()
    policy = DecisionPolicy()
    spec = _spec()
    # Warm the cache through a real decision.
    result = gate.decide({}, spec, backend_name="primary")
    cache.put({}, spec, policy, result)

    reg = builtin_degradation_plans()
    report = reg.execute(
        "serve-stale-cache",
        context={"cache_lookup": lambda: cache.get({}, spec, policy)},
        failure_code="backend_unavailable")
    assert report.outcome == "full"
    assert report.steps[0].status == "applied"
    assert "stale cached decision" in report.steps[0].note
    assert "'a'" in report.steps[0].note
    json.dumps(report.to_dict())


def test_serve_stale_cache_miss_falls_back_to_abstain():
    cache = DecisionCache()
    policy = DecisionPolicy()
    spec = _spec()
    reg = builtin_degradation_plans()
    report = reg.execute(
        "serve-stale-cache",
        context={"cache_lookup": lambda: cache.get({}, spec, policy)},
        failure_code="timeout")
    assert [s.status for s in report.steps] == ["failed", "applied"]
    assert "cache miss" in report.steps[0].note
    assert "abstaining" in report.steps[1].note
    assert report.outcome == "partial"
    assert report.degraded_gracefully is True


def test_failover_plan_with_real_fallback_chain():
    primary = StubBackend(name="primary", value="a")
    standby = StubBackend(name="standby", value="b")
    chain = FallbackChain([primary, standby])
    spec = _spec()

    def failover():
        # Primary is down; the chain routes to standby for real.
        failing = FallbackChain([standby])
        return failing.evaluate({}, spec)

    reg = builtin_degradation_plans()
    report = reg.execute("failover-then-abstain",
                         context={"failover": failover},
                         failure_code="backend_unavailable")
    assert report.outcome == "full"
    assert "failed over" in report.steps[0].note
    assert "'b'" in report.steps[0].note
    assert chain.backends[1] is standby  # the chain is real, not a prop


def test_failover_plan_when_everything_is_down_abstains():
    def failover():
        raise BackendUnavailable("standby also down")

    reg = builtin_degradation_plans()
    report = reg.execute("failover-then-abstain",
                         context={"failover": failover},
                         failure_code="backend_unavailable")
    assert [s.status for s in report.steps] == ["failed", "applied"]
    assert "standby also down" in report.steps[0].note
    assert "abstaining" in report.steps[1].note
    # The plan never answers wrong: worst case is an explicit abstain.
    assert report.degraded_gracefully is True


def test_plans_skip_gracefully_without_context():
    reg = builtin_degradation_plans()
    report = reg.execute("serve-stale-cache", failure_code="timeout")
    assert report.steps[0].status == "skipped"
    assert report.steps[1].status == "applied"  # abstain always applies
    assert report.outcome == "partial"
