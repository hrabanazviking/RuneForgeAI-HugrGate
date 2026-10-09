"""Slice 148 — adaptive-route drift detection tests."""

from __future__ import annotations

import time

import pytest

from hugrgate.adaptive.drift_detect import (
    AdaptiveDriftReport,
    AdaptiveRouteDriftDetector,
)
from hugrgate.adaptive.telemetry import RouteEvent, TelemetryStore
from hugrgate.errors import SpecError


def event(rid, chosen, quality, shadow=False, candidates=("a", "b")):
    candidates = list(candidates)
    return RouteEvent(
        request_id=rid, timestamp=time.time(),
        spec={"type": "categorical"}, features={"f": 1.0},
        candidates=candidates,
        propensities={c: 1.0 / len(candidates) for c in candidates},
        chosen=chosen, policy_version="v1", privacy_class="standard",
        outcome={"quality": quality, "source": "test"}, shadow=shadow)


def balanced(n=100):
    return [event(f"r{i}", "a" if i % 2 == 0 else "b",
                  0.9 if i % 3 else 0.4) for i in range(n)]


# --- success ---------------------------------------------------------------

def test_no_drift_on_identical_windows():
    det = AdaptiveRouteDriftDetector()
    ref = balanced(100)
    assert det.fit_reference(ref) == 100
    assert det.has_reference
    report = det.observe(balanced(100))
    assert isinstance(report, AdaptiveDriftReport)
    assert report.severity == "none"
    assert report.psi_route == pytest.approx(0.0, abs=1e-9)
    assert report.n_reference == 100 and report.n_live == 100
    assert "No significant drift" in report.advisory

def test_route_drift_detected_when_shares_shift():
    det = AdaptiveRouteDriftDetector()
    det.fit_reference(balanced(100))  # 50/50 a/b
    # Live: 95% goes to "a".
    live = [event(f"l{i}", "a" if i < 95 else "b", 0.8) for i in range(100)]
    report = det.observe(live)
    assert report.severity == "action"
    assert report.psi_route > 0.25
    assert "ACTION" in report.advisory

def test_reward_drift_detected_when_quality_collapses():
    det = AdaptiveRouteDriftDetector()
    det.fit_reference([event(f"r{i}", "a", 0.95) for i in range(100)])
    live = [event(f"l{i}", "a", 0.15) for i in range(100)]
    report = det.observe(live)
    assert report.psi_reward > 0.25
    assert report.severity == "action"

def test_mild_shift_is_watch_not_action():
    det = AdaptiveRouteDriftDetector()
    det.fit_reference(balanced(200))
    # 70/30 instead of 50/50: route PSI ≈ 0.135, inside the watch band.
    # Keep the reward mix identical so only the route signal moves.
    live = [event(f"l{i}", "a" if i < 140 else "b",
                  0.9 if i % 3 else 0.4) for i in range(200)]
    report = det.observe(live)
    assert report.severity == "watch"
    assert 0.10 <= report.psi_route < 0.25

def test_new_arm_in_live_window_handled():
    det = AdaptiveRouteDriftDetector()
    det.fit_reference(balanced(50))
    live = balanced(50) + [event(f"n{i}", "c", 0.7,
                                 candidates=("a", "b", "c"))
                           for i in range(50)]
    report = det.observe(live)
    assert "c" in report.arms
    assert report.severity == "action"  # a brand-new arm is a big shift

def test_shadow_events_excluded():
    det = AdaptiveRouteDriftDetector()
    ref = balanced(50)
    det.fit_reference(ref)
    live = balanced(50) + [event(f"s{i}", "b", 0.1, shadow=True)
                           for i in range(50)]
    report = det.observe(live)
    assert report.severity == "none"  # shadow-only shift is invisible

def test_report_serializes():
    det = AdaptiveRouteDriftDetector()
    det.fit_reference(balanced(20))
    d = det.observe(balanced(20)).to_dict()
    assert set(d) == {"psi_route", "psi_reward", "severity",
                      "n_reference", "n_live", "arms", "advisory"}

# --- failure ---------------------------------------------------------------

def test_observe_without_reference_rejected():
    with pytest.raises(SpecError):
        AdaptiveRouteDriftDetector().observe(balanced(10))

def test_empty_reference_rejected():
    with pytest.raises(SpecError):
        AdaptiveRouteDriftDetector().fit_reference([])

def test_empty_live_window_rejected():
    det = AdaptiveRouteDriftDetector()
    det.fit_reference(balanced(10))
    with pytest.raises(SpecError):
        det.observe([])

def test_bad_thresholds_rejected():
    with pytest.raises(SpecError):
        AdaptiveRouteDriftDetector(watch_threshold=0.3, alert_threshold=0.2)
    with pytest.raises(SpecError):
        AdaptiveRouteDriftDetector(reward_bins=1)
