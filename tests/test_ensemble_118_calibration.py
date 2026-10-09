"""Slice 118 — Ensemble calibration.

Temperature scaling on held-out ensemble outputs: overconfident
combinations are softened, calibrated ones left alone (T=1).
"""

from __future__ import annotations

import math

import pytest

from hugrgate.ensemble import (
    Ensemble,
    EnsembleCalibrator,
    expected_calibration_error,
)
from hugrgate.errors import BackendError, PolicyError
from ensemble_fakes import CAT_SPEC, ConstantBackend

ALPHA = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}
BETA = {"alpha": 0.2, "beta": 0.6, "gamma": 0.2}


def _overconfident(n=20):
    dists = [{"yes": 0.9, "no": 0.1}] * n
    labels = ["yes"] * 12 + ["no"] * 8
    return dists, labels


# --- success -----------------------------------------------------------------

def test_temperature_softens_overconfidence():
    dists, labels = _overconfident()
    before = expected_calibration_error(dists, labels)
    assert before == pytest.approx(0.3)
    cal = EnsembleCalibrator().fit(dists, labels, ["yes", "no"])
    assert cal.fitted
    assert cal.temperature > 1.0  # softening
    assert cal.ece_after < before
    assert cal.nll_after < cal.nll_before
    out = cal.calibrate({"yes": 0.9, "no": 0.1})
    assert out == pytest.approx({"yes": 0.6, "no": 0.4})
    assert abs(sum(out.values()) - 1.0) < 1e-9


def test_calibrated_data_gets_identity():
    dists = [{"yes": 0.6, "no": 0.4}] * 10 + [{"yes": 0.4, "no": 0.6}] * 10
    labels = ["yes"] * 6 + ["no"] * 4 + ["yes"] * 4 + ["no"] * 6
    cal = EnsembleCalibrator().fit(dists, labels, ["yes", "no"])
    assert cal.temperature == pytest.approx(1.0, abs=0.05)


def test_fit_is_deterministic():
    dists, labels = _overconfident()
    c1 = EnsembleCalibrator().fit(dists, labels, ["yes", "no"])
    c2 = EnsembleCalibrator().fit(dists, labels, ["yes", "no"])
    assert c1.temperature == c2.temperature


def test_calibrate_result_end_to_end():
    members = [ConstantBackend("a", "alpha", ALPHA),
               ConstantBackend("b", "beta", BETA)]
    ens = Ensemble(members, strategy="soft")
    result = ens.evaluate({"x": 1}, CAT_SPEC())
    cal = EnsembleCalibrator()
    # fit on the ensemble's own outputs repeated with labels
    dists = [dict(result.distribution)] * 10
    labels = ["alpha"] * 6 + ["beta"] * 4
    cal.fit(dists, labels, ["alpha", "beta", "gamma"])
    out = cal.calibrate_result(result)
    assert out.value == result.value
    assert out.calibration_profile == "ensemble:temperature"
    assert out.backend == result.backend
    assert abs(sum(out.distribution.values()) - 1.0) < 1e-9
    assert out.distribution[out.value] == pytest.approx(out.probability)
    assert 0.0 <= out.uncertainty <= 1.0
    # ensemble metadata preserved, calibration recorded
    assert out.metadata["ensemble"]["strategy"] == "soft"
    assert out.metadata["ensemble"]["calibration"]["temperature"] == \
        pytest.approx(cal.temperature)


def test_calibrate_result_passes_abstention_through():
    from hugrgate.abstain import abstain
    cal = EnsembleCalibrator().fit(*_overconfident(), ["yes", "no"])
    out = cal.calibrate_result(
        abstain(CAT_SPEC(), reason="test", backend="trio"))
    assert out.value is None
    assert out.accepted is False


def test_ece_unit():
    # 10 samples at 0.7 confidence, 7 correct -> acc == conf -> ECE 0
    dists = [{"a": 0.7, "b": 0.3}] * 10
    labels = ["a"] * 7 + ["b"] * 3
    assert expected_calibration_error(dists, labels) == pytest.approx(0.0)
    with pytest.raises(PolicyError, match="labeled data"):
        expected_calibration_error([], [])
    with pytest.raises(PolicyError, match="distributions but"):
        expected_calibration_error([{"a": 1.0}], [])


def test_to_dict():
    cal = EnsembleCalibrator().fit(*_overconfident(), ["yes", "no"])
    d = cal.to_dict()
    assert d["fitted"] is True
    assert d["temperature"] == pytest.approx(cal.temperature)
    assert d["ece_after"] < d["ece_before"]


# --- failure -----------------------------------------------------------------

def test_use_before_fit():
    cal = EnsembleCalibrator()
    assert cal.fitted is False
    with pytest.raises(BackendError, match="before fit"):
        cal.calibrate({"yes": 0.5, "no": 0.5})
    with pytest.raises(BackendError, match="before fit"):
        from hugrgate import DecisionResult
        cal.calibrate_result(DecisionResult(value="yes",
                                            probability=0.5,
                                            distribution={"yes": 0.5,
                                                          "no": 0.5}))


def test_fit_validation():
    dists, labels = _overconfident()
    with pytest.raises(PolicyError, match="needs data"):
        EnsembleCalibrator().fit([], [], ["yes", "no"])
    with pytest.raises(PolicyError, match="distributions but"):
        EnsembleCalibrator().fit(dists, labels[:-1], ["yes", "no"])
    with pytest.raises(PolicyError, match="outside classes"):
        EnsembleCalibrator().fit(dists, ["maybe"] * len(labels),
                                 ["yes", "no"])
    with pytest.raises(PolicyError, match="unique"):
        EnsembleCalibrator().fit(dists, labels, ["yes", "yes"])


# --- boundary -----------------------------------------------------------------

def test_extreme_temperature_bounds_respected():
    cal = EnsembleCalibrator().fit(*_overconfident(), ["yes", "no"])
    assert 0.05 <= cal.temperature <= 10.0
