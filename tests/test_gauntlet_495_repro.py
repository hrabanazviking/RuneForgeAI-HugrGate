"""Slice 495 — benchmark reproducibility audit.

The deterministic workload must produce identical digests across
runs (exact) and stable timing (within a noise band); a recorded
baseline JSON lets future runs detect drift.
"""

from __future__ import annotations

import json

import pytest

from hugrgate.gauntlet.repro import (
    MAX_BASELINE_DRIFT,
    ReproReport,
    compare_with_baseline,
    run_reproducibility_audit,
    run_workload,
)


def test_workload_deterministic_across_runs():
    first = run_workload(n=500, seed=495)
    second = run_workload(n=500, seed=495)
    assert first["digest"] == second["digest"]
    assert first["n"] == second["n"] == 500


def test_workload_digest_sensitive_to_seed():
    a = run_workload(n=500, seed=495)
    b = run_workload(n=500, seed=496)
    assert a["digest"] != b["digest"]


def test_audit_passes_on_this_machine():
    report = run_reproducibility_audit(runs=3, n=500, seed=495)
    assert report.deterministic
    assert report.timing_stable, f"timing CV too high: {report.timing_cv}"
    assert report.passed


def test_timing_cv_detects_instability():
    report = ReproReport(runs=[
        {"digest": "d", "ops_per_sec": 1000.0},
        {"digest": "d", "ops_per_sec": 100.0},
    ])
    assert report.deterministic
    assert not report.timing_stable
    assert not report.passed


def test_digest_mismatch_fails_audit():
    report = ReproReport(runs=[
        {"digest": "a", "ops_per_sec": 1000.0},
        {"digest": "b", "ops_per_sec": 1000.0},
    ])
    assert not report.deterministic
    assert not report.passed


def test_compare_with_baseline_match():
    # Deterministic: synthetic measurements, no machine timing.
    base = {"digest": "d", "ops_per_sec": 1000.0}
    measured = {"digest": "d", "ops_per_sec": 1150.0}
    verdict = compare_with_baseline(measured, base)
    assert verdict["digest_match"] is True
    assert verdict["within_band"] is True
    assert verdict["relative_drift"] == pytest.approx(0.15)


def test_compare_with_baseline_flags_drift():
    base = {"digest": "d", "ops_per_sec": 1000.0}
    slow = {"digest": "d",
            "ops_per_sec": 1000.0 * (1 - MAX_BASELINE_DRIFT - 0.01)}
    verdict = compare_with_baseline(slow, base)
    assert verdict["digest_match"] is True
    assert verdict["within_band"] is False
    assert verdict["relative_drift"] > MAX_BASELINE_DRIFT


def test_compare_with_baseline_flags_digest_change():
    base = {"digest": "d1", "ops_per_sec": 1000.0}
    changed = {"digest": "d2", "ops_per_sec": 1000.0}
    verdict = compare_with_baseline(changed, base)
    assert verdict["within_band"] is False


def test_baseline_json_round_trip(tmp_path):
    # The workload's measurement must survive JSON serialization
    # with its digest intact. Timing is deliberately NOT asserted
    # here — it is load-sensitive; determinism is asserted above
    # and timing stability via the audit's CV band.
    meas = run_workload(n=200, seed=495)
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(meas))
    loaded = json.loads(path.read_text())
    assert loaded["digest"] == meas["digest"]
    assert loaded["n"] == meas["n"] == 200
