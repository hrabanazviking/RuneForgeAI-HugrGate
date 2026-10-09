"""Slice 062 — availability-aware routing."""

from __future__ import annotations

import time

import pytest

from hugrgate import (
    Abstention,
    Backend,
    BackendRegistry,
    BackendUnavailable,
    DecisionPolicy,
    DecisionResult,
    DecisionSpec,
)
from hugrgate.errors import BackendError
from hugrgate.ladder import LadderRung
from hugrgate.routing import (
    AvailabilityAwarePlanner,
    AvailabilityTracker,
    DynamicRungPlanner,
    LadderRouterV2,
    RouterContext,
)


class AvailBackend(Backend):
    def __init__(self, name, prob=0.95, fail_with=None, health_status="ok",
                 health_raises=False):
        self.name = name
        self._prob = prob
        self._fail_with = fail_with
        self._health_status = health_status
        self._health_raises = health_raises
        self.calls = 0

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def health(self):
        if self._health_raises:
            raise RuntimeError("health endpoint down")
        return {"status": self._health_status, "backend": self.name}

    def evaluate(self, state, spec, context=None):
        self.calls += 1
        if self._fail_with is not None:
            raise self._fail_with
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


# -- tracker -----------------------------------------------------------------------

def test_circuit_opens_after_threshold():
    t = AvailabilityTracker(failure_threshold=3, cooldown_s=60.0)
    assert t.state("b") == "closed"
    t.record_failure("b")
    t.record_failure("b")
    assert t.state("b") == "closed"
    assert t.available(_b("b")) is None
    t.record_failure("b")
    assert t.state("b") == "open"
    reason = t.available(_b("b"))
    assert reason is not None and "circuit open" in reason


def _b(name):
    return AvailBackend(name)


def test_half_open_trial_after_cooldown():
    t = AvailabilityTracker(failure_threshold=1, cooldown_s=0.05)
    t.record_failure("b")
    assert t.state("b") == "open"
    time.sleep(0.06)
    assert t.state("b") == "half-open"
    assert t.available(_b("b")) is None  # trial allowed through
    t.record_failure("b")  # trial failed -> re-open
    assert t.state("b") == "open"


def test_success_resets_circuit():
    t = AvailabilityTracker(failure_threshold=2, cooldown_s=60.0)
    t.record_failure("b")
    t.record_success("b")
    t.record_failure("b")
    assert t.state("b") == "closed"  # counter reset, not cumulative


def test_invalid_tracker_args():
    with pytest.raises(ValueError):
        AvailabilityTracker(failure_threshold=0)
    with pytest.raises(ValueError):
        AvailabilityTracker(cooldown_s=-1)


def test_health_check_prunes_and_raises():
    t = AvailabilityTracker()
    sick = AvailBackend("sick", health_status="degraded")
    reason = t.available(sick)
    assert reason is not None and "degraded" in reason
    down = AvailBackend("down", health_raises=True)
    reason = t.available(down)
    assert reason is not None and "raised" in reason
    ok = AvailBackend("ok")
    assert t.available(ok) is None
    assert t.available(ok, check_health=False) is None


# -- planner --------------------------------------------------------------------------

def test_planner_prunes_unhealthy_and_open_circuits():
    reg = reg_of(AvailBackend("healthy"), AvailBackend("sick",
                                                       health_status="down"))
    tracker = AvailabilityTracker()
    planner = AvailabilityAwarePlanner(DynamicRungPlanner(reg), reg,
                                      tracker=tracker)
    plan = planner.plan(RouterContext.from_request({}, spec()))
    assert [n.backend_name for n in plan.nodes] == ["healthy"]
    assert plan.nodes[0].params["availability"] == "closed"


# -- router feedback -----------------------------------------------------------------------

def test_router_opens_circuit_on_repeated_failures():
    dead = AvailBackend("dead", fail_with=BackendUnavailable("gone"))
    alive = AvailBackend("alive", prob=0.99)
    reg = reg_of(dead, alive)
    tracker = AvailabilityTracker(failure_threshold=2, cooldown_s=60.0)
    router = LadderRouterV2(
        reg, rungs=[LadderRung("dead", 0.9), LadderRung("alive", 0.9)],
        availability_tracker=tracker)
    policy = DecisionPolicy(minimum_probability=0.9)
    # round 1: dead fails (1), alive wins
    assert router.decide({}, spec(), policy).backend == "alive"
    assert tracker.state("dead") == "closed"
    # round 2: dead fails (2) -> circuit opens
    assert router.decide({}, spec(), policy).backend == "alive"
    assert tracker.state("dead") == "open"
    dead_calls = dead.calls
    # round 3: dead is pruned at plan time via availability-aware planner...
    # (serial default planner doesn't prune; executor still attempts)
    assert router.decide({}, spec(), policy).backend == "alive"
    assert dead.calls == dead_calls + 1  # default planner still tries


def test_availability_planner_skips_open_circuit():
    dead = AvailBackend("dead", fail_with=BackendError("boom"))
    alive = AvailBackend("alive", prob=0.99)
    reg = reg_of(dead, alive)
    tracker = AvailabilityTracker(failure_threshold=1, cooldown_s=60.0)
    tracker.record_failure("dead")  # open the circuit directly
    router = LadderRouterV2(
        reg, rungs=[LadderRung("dead", 0.9), LadderRung("alive", 0.9)],
        planner=AvailabilityAwarePlanner(DynamicRungPlanner(reg), reg,
                                         tracker=tracker,
                                         check_health=False),
        availability_tracker=tracker)
    won = router.decide({}, spec(), DecisionPolicy(minimum_probability=0.9))
    assert won.backend == "alive"
    assert dead.calls == 0  # never touched
    assert any("availability" in r for r in router.last_plan.rationale)


def test_abstention_does_not_trip_breaker():
    from hugrgate import Abstention as Ab

    class Shy(AvailBackend):
        def evaluate(self, state, spec, context=None):
            self.calls += 1
            raise Ab("nope", reason="test")

    shy = Shy("shy")
    reg = reg_of(shy)
    tracker = AvailabilityTracker(failure_threshold=1, cooldown_s=60.0)
    router = LadderRouterV2(
        reg, rungs=[LadderRung("shy", 0.9)],
        availability_tracker=tracker)
    with pytest.raises(Abstention):
        router.decide({}, spec())
    with pytest.raises(Abstention):
        router.decide({}, spec())
    assert tracker.state("shy") == "closed"  # polite declines don't count
