"""Tests for slice 090 — calibration under shift."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.calibration.platt import PlattCalibrator
from hugrgate.calibration.shift import (
    density_ratio_weights,
    em_target_prior,
    psi,
    psi_band,
    resample_for_shift,
)
from hugrgate.errors import CalibrationError


def test_psi_detects_covariate_shift():
    rng = np.random.default_rng(0)
    source = rng.normal(0, 1, 2000).tolist()
    same = rng.normal(0, 1, 2000).tolist()
    shifted = rng.normal(1.5, 1, 2000).tolist()
    assert psi(source, same) < 0.1
    assert psi_band(psi(source, same)) == "no significant change"
    assert psi(source, shifted) > 0.25
    assert psi_band(psi(source, shifted)) == "significant change"
    with pytest.raises(CalibrationError):
        psi([], same)


def test_density_ratio_weights_direction():
    rng = np.random.default_rng(1)
    source = rng.normal(0, 1, 2000)
    target = rng.normal(1.5, 1, 2000)
    w = density_ratio_weights(source.tolist(), target.tolist())
    assert abs(sum(w) / len(w) - 1.0) < 1e-9  # mean-1 normalized
    # Source points in the target's neighborhood get up-weighted.
    w = np.asarray(w)
    assert w[source > 1.0].mean() > w[source < -1.0].mean()


def test_resample_for_shift_mimics_target():
    rng = np.random.default_rng(2)
    source = rng.normal(0, 1, 3000)
    labels = (rng.random(3000) < 0.5).astype(int)
    target = rng.normal(1.5, 1, 3000)
    rs, ry = resample_for_shift(source.tolist(), labels.tolist(),
                                target.tolist(), seed=4)
    assert len(rs) == 3000 and len(ry) == 3000
    # After resampling, the source mix looks like the target mix.
    assert psi(rs, target.tolist()) < psi(source.tolist(), target.tolist())
    assert psi_band(psi(rs, target.tolist())) != "significant change"
    with pytest.raises(CalibrationError):
        resample_for_shift([0.5], [1, 0], [0.5])


def test_em_target_prior_recovers_label_shift():
    rng = np.random.default_rng(3)
    z = rng.normal(0, 1, 4000)
    p = 1.0 / (1.0 + np.exp(-z))
    s = 1.0 / (1.0 + np.exp(-2.0 * z))
    y = (rng.random(4000) < p).astype(int)
    # Source: 20% positive; target: 60% positive (same P(x|y)).
    pos, neg = np.flatnonzero(y == 1), np.flatnonzero(y == 0)
    src_idx = np.concatenate([rng.choice(pos, 800), rng.choice(neg, 3200)])
    tgt_idx = np.concatenate([rng.choice(pos, 1200), rng.choice(neg, 800)])
    est = em_target_prior(s[src_idx].tolist(), y[src_idx].tolist(),
                          s[tgt_idx].tolist(), PlattCalibrator)
    assert est == pytest.approx(0.6, abs=0.08)
    with pytest.raises(CalibrationError):
        em_target_prior([], [], [0.5], PlattCalibrator)
