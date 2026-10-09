"""Slice 401 — threat model v2.

The STRIDE threat model is executable data: every threat names real
mitigations and covering test modules, and ``validate()`` refuses a
model with silent gaps.
"""

from __future__ import annotations

import json

import pytest

from hugrgate.security import (
    STRIDE,
    default_threat_model,
)
from hugrgate.security.threat_model import Threat, ThreatModel


def test_default_model_validates():
    model = default_threat_model()
    model.validate()  # raises on drift


def test_all_stride_categories_covered():
    grouped = default_threat_model().by_stride()
    assert set(grouped) == set(STRIDE)
    for category, threats in grouped.items():
        assert threats, f"STRIDE {category} has no threats"


def test_every_threat_has_mitigation_or_accepted_rationale():
    model = default_threat_model()
    assert model.unmitigated() == []
    for threat in model.accepted_risks():
        assert threat.rationale.strip(), threat.id


def test_risk_scores_bounded():
    for threat in default_threat_model().threats:
        assert 1 <= threat.risk <= 25
        assert threat.risk == threat.likelihood * threat.impact


def test_top_risks_sorted():
    top = default_threat_model().top_risks(3)
    risks = [t.risk for t in top]
    assert risks == sorted(risks, reverse=True)
    assert len(top) == 3


def test_coverage_report_consistent():
    report = default_threat_model().coverage_report()
    assert report["threats"] == len(default_threat_model().threats)
    assert report["unmitigated"] == []
    assert sum(report["by_stride"].values()) == report["threats"]
    assert report["max_residual_risk"] >= 0


def test_round_trip_serialization():
    model = default_threat_model()
    clone = ThreatModel.from_dict(json.loads(json.dumps(model.to_dict())))
    assert clone.version == model.version
    assert len(clone.threats) == len(model.threats)
    assert [t.id for t in clone.threats] == [t.id for t in model.threats]
    clone.validate()


def test_threat_rejects_bad_stride():
    with pytest.raises(ValueError, match="STRIDE"):
        Threat("X", "t", "nope", "decision_inputs", "d", 1, 1)


def test_threat_rejects_out_of_range_scores():
    with pytest.raises(ValueError, match="likelihood"):
        Threat("X", "t", "spoofing", "decision_inputs", "d", 0, 1)
    with pytest.raises(ValueError, match="impact"):
        Threat("X", "t", "spoofing", "decision_inputs", "d", 1, 6)


def test_validate_catches_silent_gap():
    model = default_threat_model()
    gap = Threat("T-99", "silent gap", "spoofing", "decision_inputs",
                 "no mitigations, no acceptance", 2, 2)
    model.threats.append(gap)
    with pytest.raises(ValueError, match="T-99"):
        model.validate()


def test_validate_catches_unknown_asset():
    model = default_threat_model()
    bad = Threat("T-98", "bad asset", "spoofing", "no_such_asset",
                 "d", 1, 1, mitigations=["m"], residual="mitigated")
    model.threats.append(bad)
    with pytest.raises(ValueError, match="no_such_asset"):
        model.validate()


def test_validate_catches_duplicate_ids():
    model = default_threat_model()
    dupe = Threat("T-01", "dupe", "spoofing", "decision_inputs", "d",
                  1, 1, mitigations=["m"], residual="mitigated")
    model.threats.append(dupe)
    with pytest.raises(ValueError, match="duplicate"):
        model.validate()
