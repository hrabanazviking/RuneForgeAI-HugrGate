"""Slice 463 — energy-aware tuner. Unit tests."""

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
from hugrgate.autotune.tuners.energy import EnergyAwareTuner
from hugrgate.errors import TunerError

CHOICES = ["tiny", "balanced", "giant"]


def _ctx(store, seed=5):
    return TuningContext(store=store, objectives={}, constraints=[],
                         seed=seed, mode=Mode.OFFLINE, run_id="r")


def _store(current="giant"):
    s = ConfigStore()
    s.register(TunableParameter(name="model", dtype="str", default=current,
                                choices=tuple(CHOICES)))
    return s


def _data(seed=71):
    """tiny: 0.2J/q0.70; balanced: 0.8J/q0.90; giant: 3.0J/q0.95."""
    rng = seeded_rng(seed)
    specs = {"tiny": (0.2, 0.70), "balanced": (0.8, 0.90),
             "giant": (3.0, 0.95)}
    energy, quality = {}, {}
    for ch, (e, q) in specs.items():
        energy[ch] = [rng.uniform(0.9 * e, 1.1 * e) for _ in range(50)]
        quality[ch] = [min(1.0, max(0.0, rng.gauss(q, 0.01)))
                       for _ in range(50)]
    return energy, quality


def _tuner(mode="budget", budget=1.0, **kw):
    energy, quality = _data()
    base = dict(objective_id="nrg", choices=list(CHOICES), energy_j=energy,
                quality=quality, mode=mode, energy_budget_j=budget, seed=1)
    base.update(kw)
    return EnergyAwareTuner(param="model", **base)


def test_budget_mode_picks_best_quality_under_budget():
    t = _tuner(mode="budget", budget=1.0)
    prop = t.tune(_ctx(_store("giant")))
    assert prop is not None
    # giant (3J) over budget; balanced (0.8J, q0.90) beats tiny (q0.70)
    assert prop.changes["model"] == "balanced"
    ev = prop.evidence
    assert ev["tuned"]["primary"] > ev["baseline"]["primary"]
    assert ev["measured"]["balanced"]["n_energy"] == 50


def test_budget_uses_conservative_feasibility():
    # budget exactly at giant's mean: mean + SE exceeds -> infeasible,
    # so the tuner must prefer balanced over giant
    t = _tuner(mode="budget", budget=3.0)
    prop = t.tune(_ctx(_store("tiny")))
    assert prop is not None
    assert prop.changes["model"] == "balanced"  # giant not feasible


def test_efficiency_mode():
    t = _tuner(mode="efficiency")
    prop = t.tune(_ctx(_store("giant")))
    assert prop is not None
    # quality/J: tiny 3.5 > balanced 1.125 > giant 0.317
    assert prop.changes["model"] == "tiny"
    assert prop.evidence["metric"] == "quality_per_joule"


def test_silent_when_current_is_best():
    t = _tuner(mode="budget", budget=1.0)
    assert t.tune(_ctx(_store("balanced"))) is None


def test_silent_when_nothing_feasible():
    t = _tuner(mode="budget", budget=0.01)
    assert t.tune(_ctx(_store("giant"))) is None


def test_deterministic():
    p1 = _tuner().tune(_ctx(_store(), seed=3))
    p2 = _tuner().tune(_ctx(_store(), seed=3))
    assert p1 is not None and p2 is not None
    assert p1.changes == p2.changes


def test_bad_specs_rejected():
    energy, quality = _data()
    with pytest.raises(TunerError):
        EnergyAwareTuner(param="model", objective_id="o", choices=["a"],
                         energy_j=energy, quality=quality)
    with pytest.raises(TunerError):
        EnergyAwareTuner(param="model", objective_id="o",
                         choices=list(CHOICES), energy_j=energy,
                         quality=quality, mode="nope")
    with pytest.raises(TunerError):
        EnergyAwareTuner(param="model", objective_id="o",
                         choices=list(CHOICES),
                         energy_j={"tiny": [0.1] * 3, "balanced": [0.1] * 50,
                                   "giant": [0.1] * 50},
                         quality=quality)
    with pytest.raises(TunerError):
        EnergyAwareTuner(param="model", objective_id="o",
                         choices=list(CHOICES), energy_j=energy,
                         quality=quality, energy_budget_j=-1.0)
    s = ConfigStore()
    s.register(TunableParameter(name="model", dtype="float", default=0.5,
                                lo=0.0, hi=1.0))
    with pytest.raises(TunerError):
        _tuner().tune(_ctx(s))


def test_end_to_end_offline():
    store = _store("giant")
    c = OptimizationController(store=store)
    c.register_objective("nrg", lambda values: 0.0)
    c.register_tuner(_tuner())
    run = c.run_cycle(mode=Mode.OFFLINE, seed=4)
    assert run.results[0].proposal_id != ""
    assert store.get("model") == "giant"  # offline: untouched
