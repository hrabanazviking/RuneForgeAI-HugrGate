"""Slice 461 — calibration selector. Unit tests."""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

from hugrgate.autotune.controller import (
    ConfigStore,
    Mode,
    OptimizationController,
    TunableParameter,
    TuningContext,
)
from hugrgate.autotune.tuners._base import seeded_rng
from hugrgate.autotune.tuners.calibration_select import (
    CalibrationSelectorTuner,
)
from hugrgate.calibration.autoselect import (
    DEFAULT_CANDIDATES,
    auto_select,
    paired_win,
)
from hugrgate.errors import TunerError


def _ctx(store, seed=5):
    return TuningContext(store=store, objectives={}, constraints=[],
                         seed=seed, mode=Mode.OFFLINE, run_id="r")


def _store(current="none"):
    s = ConfigStore()
    s.register(TunableParameter(name="calibrator", dtype="str",
                                default=current,
                                choices=tuple([*list(DEFAULT_CANDIDATES), "none"])))
    return s


def _miscalibrated(seed=61, n=800):
    """Systematically overconfident scores: true p, reported sqrt(p)."""
    rng = seeded_rng(seed)
    scores, labels = [], []
    for _ in range(n):
        p = rng.random()
        scores.append(p ** 0.5)  # overconfident for p in (0, 1)
        labels.append(1 if rng.random() < p else 0)
    return scores, labels


def _calibrated(seed=62, n=800):
    rng = seeded_rng(seed)
    scores, labels = [], []
    for _ in range(n):
        p = rng.random()
        scores.append(p)
        labels.append(1 if rng.random() < p else 0)
    return scores, labels


def _tuner(scores, labels, **kw):
    base = dict(objective_id="cal", scores=scores, labels=labels,
                metric="ece", seed=3)
    base.update(kw)
    return CalibrationSelectorTuner(param="calibrator", **base)


# -- hardened auto_select --------------------------------------------------------

def test_none_candidate_can_win():
    scores, labels = _calibrated()
    res = auto_select(scores, labels,
                      candidates=["platt", "isotonic", "none"],
                      metric="ece", seed=1)
    assert "none" in [r["name"] for r in res.ranking]
    # already-calibrated scores: identity should be at/near the top
    assert res.ranking[0]["name"] == "none"


def test_incumbent_kept_without_significant_win():
    scores, labels = _calibrated(seed=63)
    res = auto_select(scores, labels,
                      candidates=["platt", "isotonic", "none"],
                      metric="ece", seed=1,
                      incumbent="none", min_win=0.05)
    assert res.best == "none"
    assert res.kept_incumbent is True


def test_incumbent_replaced_on_real_win():
    scores, labels = _miscalibrated()
    res = auto_select(scores, labels,
                      candidates=["platt", "isotonic", "none"],
                      metric="ece", seed=1,
                      incumbent="none", min_win=0.0)
    assert res.best != "none"
    assert res.kept_incumbent is False
    assert res.paired_win_vs_incumbent is not None
    assert res.paired_win_vs_incumbent > 0


def test_incumbent_must_be_a_candidate():
    scores, labels = _calibrated()
    with pytest.raises(Exception):
        auto_select(scores, labels, candidates=["platt"],
                    incumbent="isotonic", seed=1)


def test_paired_win_aligned_folds():
    assert paired_win({0: 0.5, 1: 0.4}, {0: 0.6, 1: 0.6}) > 0
    assert paired_win({0: 0.5}, {1: 0.6}) is None  # no common folds


def test_backward_compatible_defaults():
    scores, labels = _calibrated(seed=64)
    r1 = auto_select(scores, labels, seed=7)
    r2 = auto_select(scores, labels, seed=7)
    assert r1.best == r2.best
    assert r1.incumbent is None and r1.kept_incumbent is False


# -- tuner ---------------------------------------------------------------------

def test_tuner_moves_off_none_on_miscalibration():
    scores, labels = _miscalibrated()
    t = _tuner(scores, labels)
    prop = t.tune(_ctx(_store("none")))
    assert prop is not None
    assert prop.changes["calibrator"] != "none"
    assert "assumptions" in prop.evidence


def test_tuner_stays_silent_when_none_wins():
    scores, labels = _calibrated(seed=65)
    t = _tuner(scores, labels, min_win=0.05)
    assert t.tune(_ctx(_store("none"))) is None


def test_statistical_win_holds_on_heldout():
    """The selected calibrator really is better calibrated, held out."""
    from hugrgate.calibration.metrics import expected_calibration_error
    scores, labels = _miscalibrated(seed=66, n=1200)
    tr_s, tr_y = scores[:800], labels[:800]
    te_s, te_y = scores[800:], labels[800:]
    t = _tuner(tr_s, tr_y)
    prop = t.tune(_ctx(_store("none")))
    assert prop is not None
    from hugrgate.calibration.registry import CalibratorRegistry
    cal = CalibratorRegistry.get(prop.changes["calibrator"])()
    cal.fit(tr_s, tr_y)
    fixed = [cal.calibrate(v) for v in te_s]
    assert expected_calibration_error(te_y, fixed) < \
        expected_calibration_error(te_y, te_s)


def test_tuner_rejects_non_str_param():
    s = ConfigStore()
    s.register(TunableParameter(name="c", dtype="float", default=0.5,
                                lo=0.0, hi=1.0))
    scores, labels = _calibrated()
    t = CalibrationSelectorTuner(param="c", objective_id="o",
                                 scores=scores, labels=labels, seed=1)
    with pytest.raises(TunerError):
        t.tune(_ctx(s))


def test_tuner_validates_data():
    with pytest.raises(TunerError):
        CalibrationSelectorTuner(param="p", objective_id="o",
                                 scores=[0.5] * 10, labels=[1] * 10,
                                 seed=1)


def test_end_to_end_offline():
    scores, labels = _miscalibrated(seed=67)
    store = _store("none")
    c = OptimizationController(store=store)
    c.register_objective("cal", lambda values: 0.0)
    c.register_tuner(_tuner(scores, labels))
    run = c.run_cycle(mode=Mode.OFFLINE, seed=4)
    assert run.results[0].proposal_id != ""
    assert store.get("calibrator") == "none"  # offline: untouched
