"""Slice 058 — energy-aware routing."""

from __future__ import annotations

import json
import os
import subprocess
import sys

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
from hugrgate.routing import (
    DynamicRungPlanner,
    EnergyAwarePlanner,
    EnergyLedger,
    EnergyModel,
    LadderRouterV2,
    RouterContext,
    RoutingOptions,
)
from hugrgate.routing.energy import DEFAULT_LOCAL_WATTS, DEFAULT_REMOTE_WATTS


class WattBackend(Backend):
    def __init__(self, name, watts=None, latency=80.0, prob=0.95,
                 remote=False, energy_j=None):
        self.name = name
        self._watts = watts
        self._latency = latency
        self._prob = prob
        self.is_remote = remote
        if energy_j is not None:
            self.estimated_energy_j = lambda: energy_j

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
        return self._latency

    def hardware_requirements(self):
        return {"power_watts": self._watts} if self._watts else {}


def reg_of(*bs):
    r = BackendRegistry()
    for b in bs:
        r.register(b)
    return r


def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def ctx(options=None):
    return RouterContext.from_request({}, spec(), DecisionPolicy(),
                                      options or RoutingOptions())


# -- model -----------------------------------------------------------------------

def test_model_uses_declared_watts_then_defaults():
    model = EnergyModel()
    declared = WattBackend("d", watts=250.0, latency=80.0)
    assert model.power_watts(declared) == 250.0
    assert model.estimate_j(declared) == pytest.approx(0.08 * 250.0)
    local = WattBackend("l", latency=100.0)
    assert model.power_watts(local) == DEFAULT_LOCAL_WATTS
    remote = WattBackend("r", latency=100.0, remote=True)
    assert model.power_watts(remote) == DEFAULT_REMOTE_WATTS
    # measured latency overrides declared
    assert model.estimate_j(local, latency_ms=50.0) == pytest.approx(
        0.05 * DEFAULT_LOCAL_WATTS)
    with pytest.raises(ValueError):
        EnergyModel(local_watts=0)


def test_custom_estimated_energy_j_wins():
    model = EnergyModel()
    b = WattBackend("c", watts=250.0, latency=80.0, energy_j=0.5)
    assert model.estimate_j(b) == 0.5


# -- ledger ------------------------------------------------------------------------

def test_ledger_accounting():
    ledger = EnergyLedger(10.0)
    assert ledger.remaining == 10.0
    assert ledger.reserve("a", 6.0)
    assert not ledger.reserve("b", 5.0)  # only 4 left
    ledger.spend(6.0)
    assert ledger.spent == pytest.approx(6.0)
    assert ledger.remaining == pytest.approx(0.0)
    with pytest.raises(ValueError):
        EnergyLedger(-1.0)
    with pytest.raises(ValueError):
        ledger.spend(-2.0)
    free = EnergyLedger(None)
    assert free.can_afford(1e12)


# -- planner -------------------------------------------------------------------------

def test_planner_prunes_over_budget_rungs():
    reg = reg_of(WattBackend("hog", watts=250.0, latency=80.0),   # 20J
                 WattBackend("lean", watts=15.0, latency=80.0))   # 1.2J
    planner = EnergyAwarePlanner(DynamicRungPlanner(reg), reg,
                                 budget_j=5.0)
    plan = planner.plan(ctx())
    assert [n.backend_name for n in plan.nodes] == ["lean"]
    assert plan.nodes[0].params["energy_estimate_j"] == pytest.approx(1.2)
    assert any("pruned 1" in r for r in plan.rationale)


def test_planner_reads_options_budget():
    reg = reg_of(WattBackend("hog", watts=250.0, latency=80.0))
    planner = EnergyAwarePlanner(DynamicRungPlanner(reg), reg)
    plan = planner.plan(ctx(RoutingOptions(max_energy_j=5.0)))
    assert plan.nodes == []
    with pytest.raises(ValueError):
        EnergyAwarePlanner(DynamicRungPlanner(reg), reg, budget_j=-1.0)


def test_empty_energy_plan_abstains():
    reg = reg_of(WattBackend("hog", watts=250.0, latency=80.0, prob=0.99))
    router = LadderRouterV2(
        reg, ladders={"categorical": [LadderRung("hog")]},
        planner=EnergyAwarePlanner(DynamicRungPlanner(reg), reg,
                                   budget_j=1.0))
    with pytest.raises(Abstention):
        router.decide({}, spec())


# -- router spend feedback ---------------------------------------------------------------

def test_router_records_measured_energy():
    reg = reg_of(WattBackend("lean", watts=15.0, latency=80.0, prob=0.99))
    ledger = EnergyLedger(None)
    router = LadderRouterV2(registry=reg, rungs=[LadderRung("lean", 0.9)],
                            energy_ledger=ledger)
    router.decide({}, spec())
    # measured latency is small (no real sleep here), energy tiny but > 0
    assert ledger.spent > 0
    assert ledger.spent < 15.0 * 1.0  # bounded by 1s x 15W


def test_no_ledger_no_energy_tracking():
    reg = reg_of(WattBackend("lean", watts=15.0, prob=0.99))
    router = LadderRouterV2(registry=reg, rungs=[LadderRung("lean", 0.9)])
    router.decide({}, spec())
    assert router.energy_ledger is None


# -- measurement artifact ------------------------------------------------------------------

def test_benchmark_artifact_energy_savings_are_real(tmp_path):
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    script = os.path.join(root, "benchmarks", "routing_energy_058.py")
    out = str(tmp_path / "routing_energy_058.json")
    proc = subprocess.run(
        [sys.executable, script, "--rounds", "4", "--out", out],
        capture_output=True, text=True, cwd=root, timeout=300)
    assert proc.returncode == 0, proc.stderr
    with open(out) as f:
        artifact = json.load(f)
    assert artifact["slice"] == "058"
    assert set(artifact["baseline"]["winners"]) == {"gpu-hog"}
    assert set(artifact["energy_aware"]["winners"]) == {"lean"}
    assert artifact["energy_aware"]["spent_j"] < \
        artifact["baseline"]["spent_j"]
    assert artifact["savings_factor"] > 1.0
    assert artifact["joules_saved"] > 0
