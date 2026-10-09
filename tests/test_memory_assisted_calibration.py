"""Slice 322 — Memory-assisted calibration, validated on controlled data."""

from __future__ import annotations

import itertools
import random

import pytest

from hugrgate.errors import MemoryError
from hugrgate.memory import (
    DecisionHistory,
    Outcome,
    assess_calibration,
    brier_score,
    calibrate_from_memory,
    expected_calibration_error,
)
from hugrgate.memory.assisted_calibration import CalibrationMap, _pava
from hugrgate.provenance import DecisionRecord


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8)
    base.update(kw)
    return DecisionRecord(**base)


def _miscalibrated_history(n: int = 2000, seed: int = 42) -> DecisionHistory:
    """Controlled data: reported p is overconfident.

    True positive rate = 0.3 + 0.4 * p (p=0.9 -> 0.66, p=0.1 -> 0.34).
    A perfect recalibration would map p -> 0.3 + 0.4*p.
    """
    rng = random.Random(seed)
    hist = DecisionHistory()
    for _ in range(n):
        p = rng.choice([0.1, 0.3, 0.5, 0.7, 0.9])
        true_rate = 0.3 + 0.4 * p
        episode = hist.record(_record(probability=p))
        hist.attach_outcome(
            episode.episode_id,
            Outcome(kind="success" if rng.random() < true_rate else "failure"))
    return hist


def test_pava_isotonic():
    fitted = _pava([0.8, 0.2, 0.6], [1.0, 1.0, 1.0])
    assert fitted == pytest.approx([0.5, 0.5, 0.6])
    assert _pava([0.1, 0.5, 0.9], [1.0, 1.0, 1.0]) == pytest.approx(
        [0.1, 0.5, 0.9])
    # weights matter: a violating pair pools to the weighted mean
    fitted = _pava([1.0, 0.0], [100.0, 1.0])
    assert fitted[0] == pytest.approx(fitted[1])
    assert fitted[0] == pytest.approx(100.0 / 101.0)


def test_brier_and_ece():
    assert brier_score([1.0, 0.0], [1, 0]) == 0.0
    assert brier_score([0.5, 0.5], [1, 0]) == pytest.approx(0.25)
    assert expected_calibration_error([0.9, 0.9], [1, 0]) == pytest.approx(
        0.4)
    assert expected_calibration_error([], []) == 0.0
    with pytest.raises(ValueError):
        brier_score([0.5], [])
    with pytest.raises(ValueError):
        brier_score([], [])
    with pytest.raises(ValueError):
        expected_calibration_error([0.5], [1], n_bins=0)


def test_calibration_improves_on_controlled_data():
    hist = _miscalibrated_history()
    cmap, validation = assess_calibration(hist, n_bins=10)
    assert isinstance(cmap, CalibrationMap)
    # statistical validation: correction must reduce both metrics
    assert validation.ece_after < validation.ece_before
    assert validation.brier_after < validation.brier_before
    assert validation.n_fit + validation.n_validate == 2000
    assert validation.n_fit == pytest.approx(1400, abs=2)
    # the learned map approximates the true rate function
    assert cmap.correct(0.9) == pytest.approx(0.66, abs=0.08)
    assert cmap.correct(0.1) == pytest.approx(0.34, abs=0.08)
    # monotone non-decreasing
    corrected = [cmap.correct(p / 100) for p in range(101)]
    assert all(b >= a for a, b in itertools.pairwise(corrected))


def test_calibrate_from_memory_map_shape():
    hist = _miscalibrated_history(n=500)
    cmap = calibrate_from_memory(hist, n_bins=5)
    assert len(cmap.bin_centers) == len(cmap.corrected) == 5
    d = cmap.to_dict()
    assert len(d["bin_centers"]) == 5


def test_correct_validation_and_clamping():
    cmap = CalibrationMap(bin_centers=(0.2, 0.8), corrected=(0.3, 0.7))
    assert cmap.correct(0.0) == 0.3
    assert cmap.correct(1.0) == 0.7
    assert cmap.correct(0.5) == pytest.approx(0.5)
    with pytest.raises(ValueError):
        cmap.correct(1.5)
    with pytest.raises(ValueError):
        CalibrationMap(bin_centers=(0.5,), corrected=())
    with pytest.raises(ValueError):
        CalibrationMap(bin_centers=(), corrected=())


def test_no_labeled_episodes_raises():
    hist = DecisionHistory()
    hist.record(_record())
    with pytest.raises(MemoryError):
        calibrate_from_memory(hist)
    with pytest.raises(MemoryError):
        assess_calibration(hist)
    with pytest.raises(ValueError):
        calibrate_from_memory(_miscalibrated_history(n=10), n_bins=0)
    with pytest.raises(ValueError):
        assess_calibration(_miscalibrated_history(n=10), fit_fraction=1.0)


def test_single_labeled_episode_split_raises():
    hist = DecisionHistory()
    episode = hist.record(_record())
    hist.attach_outcome(episode.episode_id, Outcome(kind="success"))
    with pytest.raises(MemoryError):
        assess_calibration(hist)


def test_validation_to_dict():
    hist = _miscalibrated_history(n=600)
    _, validation = assess_calibration(hist)
    d = validation.to_dict()
    assert d["n_fit"] + d["n_validate"] == 600
    # Brier is unbinned: the robust improvement signal on small splits
    assert d["brier_after"] < d["brier_before"]
