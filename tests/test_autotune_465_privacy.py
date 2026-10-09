"""Slice 465 — privacy-constrained tuner. Unit tests."""

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
from hugrgate.autotune.tuners.privacy import PrivacyConstrainedTuner
from hugrgate.errors import TunerError

CHOICES = ["raw", "redacted", "dp_noisy"]


def _ctx(store, seed=5, max_class="forbidden"):
    return TuningContext(store=store, objectives={}, constraints=[],
                         seed=seed, mode=Mode.OFFLINE, run_id="r",
                         data={"max_privacy_class": max_class})


def _store(current="raw"):
    s = ConfigStore()
    s.register(TunableParameter(name="telemetry", dtype="str",
                                default=current, choices=tuple(CHOICES)))
    return s


def _data(seed=91):
    """raw: sensitive/u0.95/epinf; redacted: standard/u0.88/ep0.5;
    dp_noisy: standard/u0.80/ep0.1."""
    rng = seeded_rng(seed)
    specs = {"raw": 0.95, "redacted": 0.88, "dp_noisy": 0.80}
    return {ch: [min(1.0, max(0.0, rng.gauss(q, 0.01))) for _ in range(50)]
            for ch, q in specs.items()}


def _tuner(mode="budget", max_class="forbidden", **kw):
    base = dict(objective_id="priv", choices=list(CHOICES),
                privacy_class={"raw": "sensitive", "redacted": "standard",
                               "dp_noisy": "standard"},
                epsilon={"raw":  float("inf"), "redacted": 0.5,
                         "dp_noisy": 0.1},
                utility=_data(), mode=mode, epsilon_budget=1.0, seed=1)
    base.update(kw)
    return PrivacyConstrainedTuner(param="telemetry", **base)


def test_budget_mode_respects_epsilon():
    t = _tuner(mode="budget", epsilon_budget=1.0)
    prop = t.tune(_ctx(_store("dp_noisy")))
    assert prop is not None
    # raw has infinite epsilon -> excluded; redacted u0.88 wins
    assert prop.changes["telemetry"] == "redacted"
    assert prop.evidence["feasible_choices"] == ["redacted", "dp_noisy"]


def test_classification_ceiling_excludes():
    # deployment ceiling "standard": "raw" (sensitive) is out even
    # with an infinite epsilon budget
    t = _tuner(mode="budget", epsilon_budget=float("inf"))
    prop = t.tune(_ctx(_store("dp_noisy"), max_class="standard"))
    assert prop is not None
    assert prop.changes["telemetry"] == "redacted"
    assert "raw" not in prop.evidence["feasible_choices"]
    assert prop.evidence["max_privacy_class"] == "standard"


def test_infeasible_incumbent_escapes():
    t = _tuner(mode="budget", epsilon_budget=1.0)
    prop = t.tune(_ctx(_store("raw")))  # raw: infinite epsilon
    assert prop is not None
    assert prop.evidence["current_feasible"] is False
    assert prop.evidence["baseline"]["primary"] == float("-inf")
    assert prop.changes["telemetry"] == "redacted"


def test_minimize_mode():
    t = _tuner(mode="minimize", utility_floor=0.85)
    prop = t.tune(_ctx(_store("raw")))
    assert prop is not None
    # redacted (ep 0.5, u0.88) meets floor cheaper than... dp_noisy
    # u0.80 < 0.85 fails the floor; redacted wins
    assert prop.changes["telemetry"] == "redacted"
    assert prop.evidence["metric"] == "neg_epsilon"


def test_silent_when_optimal_or_empty():
    assert _tuner().tune(_ctx(_store("redacted"))) is None
    t = _tuner(mode="budget", epsilon_budget=0.01)
    assert t.tune(_ctx(_store("dp_noisy"))) is None  # nothing feasible


def test_bad_ceiling_rejected():
    with pytest.raises(TunerError):
        _tuner().tune(_ctx(_store(), max_class="nope"))


def test_bad_specs_rejected():
    with pytest.raises(TunerError):
        PrivacyConstrainedTuner(param="t", objective_id="o",
                                choices=["a"],
                                privacy_class={"a": "public"},
                                epsilon={"a": 0.0},
                                utility={"a": [0.5] * 30})
    with pytest.raises(TunerError):
        _tuner(privacy_class={"raw": "mystery", "redacted": "standard",
                              "dp_noisy": "standard"})
    with pytest.raises(TunerError):
        _tuner(epsilon={"raw": -1.0, "redacted": 0.5, "dp_noisy": 0.1})
    with pytest.raises(TunerError):
        _tuner(mode="minimize", utility_floor=2.0)


def test_end_to_end_offline():
    store = _store("dp_noisy")
    c = OptimizationController(store=store)
    c.register_objective("priv", lambda values: 0.0)
    c.register_tuner(_tuner())
    run = c.run_cycle(mode=Mode.OFFLINE, seed=4,
                      data={"max_privacy_class": "forbidden"})
    assert run.results[0].proposal_id != ""
    assert store.get("telemetry") == "dp_noisy"  # offline: untouched
