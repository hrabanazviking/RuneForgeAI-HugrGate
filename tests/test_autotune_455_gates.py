"""Slice 455 — confidence-gate tuner. Unit tests."""

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
from hugrgate.autotune.tuners.gates import (
    ConfidenceGateTuner,
    wilson_lower_bound,
)
from hugrgate.errors import TunerError


def _ctx(store, seed=5):
    return TuningContext(store=store, objectives={}, constraints=[],
                         seed=seed, mode=Mode.OFFLINE, run_id="r")


def _store(tau=0.95):
    s = ConfigStore()
    s.register(TunableParameter(name="tau", dtype="float", default=tau,
                                lo=0.0, hi=1.0))
    return s


def _calibrated(seed=21, n=2000):
    """Confidences that mean what they say: correct w.p. = confidence."""
    rng = seeded_rng(seed)
    out = []
    for _ in range(n):
        c = rng.choice([0.55, 0.65, 0.75, 0.85, 0.95])
        out.append((c, rng.random() < c))
    rng.shuffle(out)
    return out


def test_wilson_sanity():
    # 95/100 successes: lower bound below 0.95, above 0.85
    lb = wilson_lower_bound(95, 100, 0.05)
    assert 0.85 < lb < 0.95
    assert wilson_lower_bound(0, 0) == 0.0
    assert wilson_lower_bound(100, 100) < 1.0  # never claims certainty
    with pytest.raises(TunerError):
        wilson_lower_bound(5, 10, alpha=1.5)


def test_wilson_matches_known_value():
    # Textbook: 60/100 at 95% -> [0.502, 0.691]; check lower bound.
    assert wilson_lower_bound(60, 100, 0.05) == pytest.approx(0.502, abs=0.002)


def test_accuracy_floor_finds_high_coverage_tau():
    t = ConfidenceGateTuner(param="tau", objective_id="cov",
                            dataset=_calibrated(), mode="accuracy_floor",
                            floor=0.8, alpha=0.05, seed=3)
    prop = t.tune(_ctx(_store(tau=0.95)))
    assert prop is not None
    # tau=0.95 answers only the top bin (~20% coverage); the tuner
    # should open the gate while the Wilson LB stays >= 0.8
    assert prop.evidence["heldout_wilson_lb"] >= 0.8
    assert prop.evidence["heldout_coverage"] > 0.5
    assert prop.changes["tau"] < 0.95
    assert "assumptions" in prop.evidence


def test_guarantee_holds_on_fresh_data():
    """The statistical claim, checked on data the tuner never saw."""
    t = ConfidenceGateTuner(param="tau", objective_id="cov",
                            dataset=_calibrated(seed=21), mode="accuracy_floor",
                            floor=0.8, alpha=0.05, seed=3)
    prop = t.tune(_ctx(_store(tau=0.95)))
    assert prop is not None
    tau = prop.changes["tau"]
    fresh = _calibrated(seed=999, n=5000)
    answered = [ok for c, ok in fresh if c >= tau]
    k = sum(answered)
    lb = wilson_lower_bound(k, len(answered), 0.05)
    assert lb >= 0.8  # the guarantee transfers to fresh i.i.d. data


def test_impossible_floor_stays_silent():
    t = ConfidenceGateTuner(param="tau", objective_id="cov",
                            dataset=_calibrated(), mode="accuracy_floor",
                            floor=0.999, alpha=0.05, seed=3)
    assert t.tune(_ctx(_store())) is None


def test_coverage_target_mode():
    t = ConfidenceGateTuner(param="tau", objective_id="acc",
                            dataset=_calibrated(), mode="coverage_target",
                            target=0.5, alpha=0.05, seed=3)
    prop = t.tune(_ctx(_store(tau=0.5)))
    assert prop is not None
    assert prop.evidence["heldout_coverage"] >= 0.5 - 1e-9


def test_bad_specs_rejected():
    with pytest.raises(TunerError):
        ConfidenceGateTuner(param="tau", objective_id="o", dataset=_calibrated(),
                            mode="nope", seed=1)
    with pytest.raises(TunerError):
        ConfidenceGateTuner(param="tau", objective_id="o",
                            dataset=[(0.5, True)] * 10, seed=1)
    with pytest.raises(TunerError):
        ConfidenceGateTuner(param="tau", objective_id="o",
                            dataset=[(1.5, True)] * 50, seed=1)
    s = ConfigStore()
    s.register(TunableParameter(name="n", dtype="int", default=1,
                                lo=0, hi=2))
    with pytest.raises(TunerError):
        ConfidenceGateTuner(param="n", objective_id="o",
                            dataset=_calibrated(),
                            seed=1).tune(_ctx(s))


def test_end_to_end_offline():
    store = _store(tau=0.95)
    c = OptimizationController(store=store)
    c.register_objective("cov", lambda values: 0.0)
    c.register_tuner(ConfidenceGateTuner(
        param="tau", objective_id="cov", dataset=_calibrated(), seed=3))
    run = c.run_cycle(mode=Mode.OFFLINE, seed=7)
    assert run.results[0].proposal_id != ""
    assert store.get("tau") == 0.95  # offline: untouched
