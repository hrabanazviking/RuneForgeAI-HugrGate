"""Tests for slice 085 — coverage guarantees tooling."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.calibration.conformal import ConformalClassifier
from hugrgate.calibration.coverage import (
    CoverageCertificate,
    clopper_pearson,
    hoeffding_lower_bound,
    required_n,
    validate_coverage,
)
from hugrgate.calibration.sets import cumulative_set
from hugrgate.errors import CalibrationError


def test_clopper_pearson_covers():
    # Simulation: 2000 repetitions of Binomial(200, 0.9); the 95% CP
    # interval should contain 0.9 about 95% of the time (≥ 93% to be safe).
    rng = np.random.default_rng(12)
    hits = rng.binomial(200, 0.9, size=2000)
    inside = sum(1 for k in hits
                 if clopper_pearson(int(k), 200)[0] <= 0.9
                 <= clopper_pearson(int(k), 200)[1])
    assert inside / 2000 >= 0.93
    # Edge cases: all misses / all hits.
    assert clopper_pearson(0, 50)[0] == 0.0
    assert clopper_pearson(50, 50)[1] == 1.0
    lo, hi = clopper_pearson(45, 50)
    assert lo < 0.9 < hi
    with pytest.raises(CalibrationError):
        clopper_pearson(51, 50)
    with pytest.raises(CalibrationError):
        clopper_pearson(5, 0)


def test_hoeffding_bound_sane():
    b = hoeffding_lower_bound(90, 100)
    assert 0.0 < b < 0.9
    assert hoeffding_lower_bound(100, 100, delta=0.5) < 1.0
    with pytest.raises(CalibrationError):
        hoeffding_lower_bound(5, 100, delta=1.5)


def test_certificate_validates_good_and_bad_sets():
    rng = np.random.default_rng(5)
    names = ["a", "b", "c"]
    probas = [dict(zip(names, rng.dirichlet([3, 3, 3]))) for _ in range(600)]
    labels = [names[int((rng.random() < np.cumsum(list(p.values()))).argmax())]
              for p in probas]
    cc = ConformalClassifier(alpha=0.1).fit(probas[:300], labels[:300])
    sets = [cumulative_set(p, 0.95) for p in probas[300:]]
    cert = validate_coverage(sets, labels[300:], target=0.9)
    assert isinstance(cert, CoverageCertificate)
    assert cert.n == 300
    assert cert.as_dict()["extra"]["holds"] is True
    assert cert.validates(0.9)
    # Absurd target fails.
    assert not cert.validates(0.999)
    # Hoeffding method also works.
    cert_h = validate_coverage(sets, labels[300:], target=0.8,
                               method="hoeffding")
    assert cert_h.validates(0.8)
    with pytest.raises(CalibrationError):
        validate_coverage(sets, labels[:10], target=0.9)


def test_required_n():
    n = required_n(0.1)
    assert isinstance(n, int) and n > 100
    # Tighter width needs more samples; check monotonicity.
    assert required_n(0.05) > required_n(0.1) > required_n(0.2)
    with pytest.raises(CalibrationError):
        required_n(1.5)
