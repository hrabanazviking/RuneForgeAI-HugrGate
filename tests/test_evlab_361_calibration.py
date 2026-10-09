"""Slice 361 — Calibration comparisons.

Covers: identity baseline, temperature fit improving ECE on
overconfident scores, histogram binning mapping, unfitted-use
rejection, argument validation, ECE/NLL math, comparison ranking and
best/improvement queries, package-calibrator adapter (ml extra),
backend-level comparison end-to-end, and serialization round-trip.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionSpec
from hugrgate.errors import CalibrationError, EvalError
from hugrgate.evlab import (
    CalibrationComparison,
    HistogramBinningCalibrator,
    IdentityCalibrator,
    PackageCalibrator,
    TemperatureCalibrator,
    compare_backend_calibration,
    compare_calibrators,
    expected_calibration_error,
)

pytest.importorskip("numpy")  # the package-adapter path needs the ml extra


def _overconfident(n=200, seed=11):
    """0.9 confidence, 60% correct — the classic miscalibration."""
    import random
    rng = random.Random(seed)
    confs = [0.9] * n
    correct = [1 if rng.random() < 0.6 else 0 for _ in range(n)]
    return confs, correct


def _split(confs, correct, seed=5):
    import random
    order = list(range(len(confs)))
    random.Random(seed).shuffle(order)
    cut = len(order) // 2
    return ([confs[i] for i in order[:cut]],
            [correct[i] for i in order[:cut]],
            [confs[i] for i in order[cut:]],
            [correct[i] for i in order[cut:]])


# --- calibrators --------------------------------------------------------------------

def test_identity_is_baseline():
    cal = IdentityCalibrator()
    cal.fit([0.9, 0.1], [1, 0])
    assert cal.calibrate(0.9) == pytest.approx(0.9)


def test_temperature_improves_overconfident_ece():
    confs, correct = _overconfident()
    cc, cy, ec, ey = _split(confs, correct)
    temp = TemperatureCalibrator()
    temp.fit(cc, cy)
    assert temp.temperature > 1.0  # overconfidence -> soften
    ident = IdentityCalibrator()
    ident.fit(cc, cy)
    ece_raw = expected_calibration_error(
        ey, [ident.calibrate(p) for p in ec])
    ece_cal = expected_calibration_error(
        ey, [temp.calibrate(p) for p in ec])
    # All confidences are 0.9: single-bin ECE == |acc - 0.9| exactly.
    assert ece_raw == pytest.approx(abs(sum(ey) / len(ey) - 0.9))
    assert ece_raw > 0.2  # genuinely miscalibrated
    assert ece_cal < ece_raw - 0.05


def test_temperature_preserves_ranking():
    temp = TemperatureCalibrator()
    temp.fit([0.9, 0.8, 0.7, 0.6], [1, 1, 0, 0])
    cal = [temp.calibrate(p) for p in (0.9, 0.8, 0.7, 0.6)]
    assert cal == sorted(cal, reverse=True)


def test_histogram_binning_maps_to_bin_accuracy():
    cal = HistogramBinningCalibrator(n_bins=2)
    # Bin [0, .5): always wrong; bin [.5, 1]: always right.
    cal.fit([0.1, 0.2, 0.3, 0.9, 0.8, 0.7], [0, 0, 0, 1, 1, 1])
    assert cal.calibrate(0.15) == pytest.approx(0.0)
    assert cal.calibrate(0.85) == pytest.approx(1.0)


def test_histogram_bad_bins_rejected():
    with pytest.raises(EvalError):
        HistogramBinningCalibrator(n_bins=1)


def test_unfitted_use_rejected():
    with pytest.raises(EvalError):
        TemperatureCalibrator().calibrate(0.5)
    with pytest.raises(EvalError):
        HistogramBinningCalibrator().calibrate(0.5)


def test_fit_validation():
    temp = TemperatureCalibrator()
    with pytest.raises(EvalError):
        temp.fit([0.9], [1])  # too few
    with pytest.raises(EvalError):
        temp.fit([0.9, 0.8], [1])  # length mismatch
    with pytest.raises(EvalError):
        temp.fit([1.5, 0.8], [1, 0])  # out of range
    with pytest.raises(EvalError):
        temp.fit([0.9, 0.8], [1, 2])  # bad label


# --- ECE math --------------------------------------------------------------------------

def test_ece_perfect_and_worst():
    assert expected_calibration_error([1, 1, 0, 0], [1.0, 1.0, 0.0, 0.0]) \
        == pytest.approx(0.0)
    assert expected_calibration_error([1, 1, 0, 0], [0.0, 0.0, 1.0, 1.0]) \
        == pytest.approx(1.0)


def test_ece_validation():
    with pytest.raises(EvalError):
        expected_calibration_error([1], [0.5, 0.5])
    with pytest.raises(EvalError):
        expected_calibration_error([], [])
    with pytest.raises(EvalError):
        expected_calibration_error([1], [0.5], n_bins=0)


# --- compare_calibrators -------------------------------------------------------------------

def test_compare_ranks_temperature_best():
    confs, correct = _overconfident()
    cc, cy, ec, ey = _split(confs, correct)
    comp = compare_calibrators(cc, cy, ec, ey,
                               [IdentityCalibrator(),
                                TemperatureCalibrator(),
                                HistogramBinningCalibrator()])
    assert comp.best == "temperature"
    assert comp.ranking[0][0] == "temperature"
    assert comp.improvement_over_identity("temperature") > 0.05
    assert comp.improvement_over_identity("identity") == pytest.approx(0.0)
    assert comp.improvement_over_identity("ghost") is None
    assert comp.n_calib == len(cc)
    assert comp.n_eval == len(ec)


def test_compare_needs_calibrators():
    with pytest.raises(EvalError):
        compare_calibrators([0.9, 0.8], [1, 0], [0.9], [1], [])


def test_compare_eval_empty_rejected():
    with pytest.raises(EvalError):
        compare_calibrators([0.9, 0.8], [1, 0], [], [],
                            [IdentityCalibrator()])


def test_comparison_roundtrip():
    confs, correct = _overconfident()
    cc, cy, ec, ey = _split(confs, correct)
    comp = compare_calibrators(cc, cy, ec, ey, [IdentityCalibrator()])
    clone = CalibrationComparison.from_dict(comp.to_dict())
    assert clone.to_dict() == comp.to_dict()
    assert clone.best == "identity"


# --- package adapter -------------------------------------------------------------------------

def test_package_calibrator_wraps_temperature():
    from hugrgate.calibration.temperature import (
        TemperatureCalibrator as PkgTemp,
    )
    adapter = PackageCalibrator(PkgTemp())
    assert adapter.name == "package:temperature"
    confs, correct = _overconfident()
    cc, cy, ec, ey = _split(confs, correct)
    adapter.fit(cc, cy)
    cal = [adapter.calibrate(p) for p in ec]
    assert all(0.0 < p < 1.0 for p in cal)
    ident = IdentityCalibrator()
    ident.fit(cc, cy)
    assert expected_calibration_error(ey, cal) < \
        expected_calibration_error(ey, [ident.calibrate(p) for p in ec])


def test_package_calibrator_without_numpy():
    import hugrgate.calibration.temperature as pkg
    real_np = pkg.np
    pkg.np = None
    try:
        adapter = PackageCalibrator(pkg.TemperatureCalibrator())
        with pytest.raises(CalibrationError):
            adapter.fit([0.9, 0.8], [1, 0])
    finally:
        pkg.np = real_np


# --- backend-level ------------------------------------------------------------------------------

def _miscalibrated_dataset(n=120):
    return {
        "name": "calib-smoke",
        "version": "1.0.0",
        "spec": DecisionSpec(type="categorical",
                             options=["a", "b"]).to_dict(),
        # 60% "a": the overconfident stub (p=0.95) is miscalibrated.
        "items": [{"state": {"x": i},
                   "expected": "a" if i % 10 < 6 else "b"}
                  for i in range(n)],
    }


def test_compare_backend_calibration_end_to_end(gate_with_stub,
                                               stub_backend):
    from tests.conftest import StubBackend
    gate_with_stub.register(
        StubBackend(name="overconf", value="a", probability=0.95))
    results = compare_backend_calibration(
        _miscalibrated_dataset(), gate_with_stub,
        ["overconf"],
        [TemperatureCalibrator, HistogramBinningCalibrator],
        seed=9)
    comp = results["overconf"]
    assert set(comp.methods) == {"identity", "temperature",
                                 "histogram_binning"}
    assert comp.best in ("temperature", "histogram_binning")
    assert comp.improvement_over_identity(comp.best) > 0.05


def test_compare_backend_calibration_validation(gate_with_stub):
    with pytest.raises(EvalError):
        compare_backend_calibration(_miscalibrated_dataset(),
                                    gate_with_stub, [],
                                    [TemperatureCalibrator])
    with pytest.raises(EvalError):
        compare_backend_calibration(_miscalibrated_dataset(),
                                    gate_with_stub, ["stub"], [])
    with pytest.raises(EvalError):
        compare_backend_calibration(_miscalibrated_dataset(),
                                    gate_with_stub, ["stub"],
                                    [TemperatureCalibrator],
                                    calib_frac=1.5)
