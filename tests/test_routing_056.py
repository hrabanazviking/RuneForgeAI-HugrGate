"""Slice 056 — latency-aware routing."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from hugrgate import (
    Backend,
    BackendRegistry,
    DecisionPolicy,
    DecisionResult,
    DecisionSpec,
)
from hugrgate.ladder import LadderRung
from hugrgate.routing import (
    DynamicRungPlanner,
    LadderRouterV2,
    LatencyAwarePlanner,
    LatencyTracker,
    RouterContext,
)


class LatBackend(Backend):
    def __init__(self, name, declared=100.0, prob=0.95):
        self.name = name
        self._declared = declared
        self._prob = prob

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

    def estimated_latency(self):
        return self._declared


def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


# -- tracker ---------------------------------------------------------------------

def test_ema_math_and_sample_gate():
    t = LatencyTracker(alpha=0.5, min_samples=3)
    b = LatBackend("b", declared=100.0)
    assert t.measured("b") is None
    assert t.estimate(b) == 100.0  # falls back to declared
    t.record("b", 20.0)
    t.record("b", 20.0)
    assert t.measured("b") is None  # still gated
    t.record("b", 40.0)  # ema: 20 -> 20 -> 30
    assert t.measured("b") == pytest.approx(30.0)
    assert t.estimate(b) == pytest.approx(30.0)
    with pytest.raises(ValueError):
        t.record("b", -1.0)
    with pytest.raises(ValueError):
        LatencyTracker(alpha=0.0)
    with pytest.raises(ValueError):
        LatencyTracker(min_samples=0)


# -- planner ---------------------------------------------------------------------

def test_planner_prunes_on_measured_latency():
    reg = BackendRegistry()
    reg.register(LatBackend("slow", declared=10.0))
    reg.register(LatBackend("fast", declared=10.0))
    tracker = LatencyTracker(min_samples=1)
    tracker.record("slow", 500.0)  # measured truth: too slow
    planner = LatencyAwarePlanner(DynamicRungPlanner(reg), reg,
                                  tracker=tracker)
    ctx = RouterContext.from_request(
        {}, spec(), DecisionPolicy(maximum_latency_ms=250.0))
    plan = planner.plan(ctx)
    assert [n.backend_name for n in plan.nodes] == ["fast"]
    assert any("latency-pruned" in r for r in plan.rationale)
    assert plan.nodes[0].params["latency_estimate_ms"] == pytest.approx(10.0)


def test_planner_keeps_all_when_no_budget():
    reg = BackendRegistry()
    reg.register(LatBackend("a"))
    planner = LatencyAwarePlanner(DynamicRungPlanner(reg), reg)
    plan = planner.plan(RouterContext.from_request({}, spec()))
    assert [n.backend_name for n in plan.nodes] == ["a"]
    assert any("no rungs latency-pruned" in r for r in plan.rationale)


# -- router integration ------------------------------------------------------------

def test_router_feeds_tracker_after_climb():
    reg = BackendRegistry()
    reg.register(LatBackend("a", declared=5.0, prob=0.99))
    tracker = LatencyTracker(min_samples=1)
    router = LadderRouterV2(
        registry=reg, rungs=[LadderRung("a", 0.9)],
        latency_tracker=tracker)
    router.decide({}, spec())
    assert tracker.samples("a") >= 1
    assert tracker.measured("a") is not None
    assert tracker.measured("a") < 50.0  # real measurement, near-instant


def test_no_tracker_no_recording():
    reg = BackendRegistry()
    reg.register(LatBackend("a", prob=0.99))
    router = LadderRouterV2(registry=reg, rungs=[LadderRung("a", 0.9)])
    router.decide({}, spec())  # must not raise without a tracker
    assert router.latency_tracker is None


# -- measurement artifact ------------------------------------------------------------

def test_benchmark_artifact_is_real_and_beats_baseline(tmp_path):
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    script = os.path.join(root, "benchmarks", "routing_latency_056.py")
    out = str(tmp_path / "routing_latency_056.json")
    proc = subprocess.run(
        [sys.executable, script, "--rounds", "6", "--out", out],
        capture_output=True, text=True, cwd=root, timeout=300)
    assert proc.returncode == 0, proc.stderr
    with open(out) as f:
        artifact = json.load(f)
    assert artifact["slice"] == "056"
    assert artifact["rounds"] == 6
    for name, row in artifact["per_backend"].items():
        assert row["tracker_samples"] >= 3, name
        # measured EMA must be closer to truth than the flat 100ms default
        assert (row["measured_abs_error_ms"]
                < row["declared_abs_error_ms"]), name
    assert artifact["error_reduction_factor"] > 1.0
