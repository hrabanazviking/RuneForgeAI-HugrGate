"""Slice 464 — cost-aware tuner. Unit tests."""

from __future__ import annotations

import pytest

from hugrgate.autotune.controller import (
    ConfigStore,
    Mode,
    OptimizationController,
    TunableParameter,
    TuningContext,
)
from hugrgate.autotune.tuners._base import seeded_rng
from hugrgate.autotune.tuners.cost import CostAwareTuner
from hugrgate.errors import TunerError

CHOICES = ["free", "pro", "enterprise"]


def _ctx(store, seed=5):
    return TuningContext(store=store, objectives={}, constraints=[],
                         seed=seed, mode=Mode.OFFLINE, run_id="r")


def _store(current="enterprise"):
    s = ConfigStore()
    s.register(TunableParameter(name="backend", dtype="str",
                                default=current, choices=tuple(CHOICES)))
    return s


def _data(seed=81):
    """free: $0.001/q0.70; pro: $0.02/q0.88; enterprise: $0.10/q0.93."""
    rng = seeded_rng(seed)
    specs = {"free": (0.001, 0.70), "pro": (0.02, 0.88),
             "enterprise": (0.10, 0.93)}
    cost, quality = {}, {}
    for ch, (c, q) in specs.items():
        cost[ch] = [rng.uniform(0.9 * c, 1.1 * c) for _ in range(50)]
        quality[ch] = [min(1.0, max(0.0, rng.gauss(q, 0.01)))
                       for _ in range(50)]
    return cost, quality


def _tuner(mode="budget", **kw):
    cost, quality = _data()
    base = dict(objective_id="usd", choices=list(CHOICES), cost=cost,
                quality=quality, mode=mode, seed=1)
    base.update(kw)
    return CostAwareTuner(param="backend", **base)


def test_budget_mode():
    t = _tuner(mode="budget", cost_budget=0.05)
    prop = t.tune(_ctx(_store("enterprise")))
    assert prop is not None
    # enterprise ($0.10) over budget; pro ($0.02, q0.88) beats free
    assert prop.changes["backend"] == "pro"
    assert prop.evidence["current_feasible"] is False


def test_floor_mode_picks_cheapest_meeting_floor():
    t = _tuner(mode="floor", quality_floor=0.85)
    prop = t.tune(_ctx(_store("free")))
    assert prop is not None
    # free q0.70 < 0.85 infeasible; pro is cheapest feasible
    assert prop.changes["backend"] == "pro"
    assert prop.evidence["metric"] == "neg_mean_cost"


def test_floor_mode_statistical_guarantee():
    """The guarantee is mean - 1.96*SE >= floor on measured samples."""
    t = _tuner(mode="floor", quality_floor=0.85)
    prop = t.tune(_ctx(_store("enterprise")))
    assert prop is not None
    m = prop.evidence["measured"]["pro"]
    assert m["mean_quality"] - 1.96 * m["se_quality"] >= 0.85


def test_silent_when_optimal_or_infeasible():
    assert _tuner(mode="budget", cost_budget=0.05).tune(
        _ctx(_store("pro"))) is None
    assert _tuner(mode="budget", cost_budget=0.0001).tune(
        _ctx(_store("enterprise"))) is None
    assert _tuner(mode="floor", quality_floor=0.999).tune(
        _ctx(_store("enterprise"))) is None


def test_deterministic():
    p1 = _tuner(mode="floor", quality_floor=0.85).tune(_ctx(_store(), seed=3))
    p2 = _tuner(mode="floor", quality_floor=0.85).tune(_ctx(_store(), seed=3))
    assert p1 is not None and p2 is not None
    assert p1.changes == p2.changes


def test_bad_specs_rejected():
    cost, quality = _data()
    with pytest.raises(TunerError):
        CostAwareTuner(param="backend", objective_id="o", choices=["a"],
                       cost=cost, quality=quality)
    with pytest.raises(TunerError):
        CostAwareTuner(param="backend", objective_id="o",
                       choices=list(CHOICES), cost=cost, quality=quality,
                       mode="nope")
    with pytest.raises(TunerError):
        CostAwareTuner(param="backend", objective_id="o",
                       choices=list(CHOICES), cost=cost, quality=quality,
                       quality_floor=1.5)
    with pytest.raises(TunerError):
        CostAwareTuner(param="backend", objective_id="o",
                       choices=list(CHOICES),
                       cost={"free": [0.1] * 5, "pro": [0.1] * 50,
                             "enterprise": [0.1] * 50},
                       quality=quality)


def test_end_to_end_offline():
    store = _store("enterprise")
    c = OptimizationController(store=store)
    c.register_objective("usd", lambda values: 0.0)
    c.register_tuner(_tuner(mode="budget", cost_budget=0.05))
    run = c.run_cycle(mode=Mode.OFFLINE, seed=4)
    assert run.results[0].proposal_id != ""
    assert store.get("backend") == "enterprise"  # offline: untouched
