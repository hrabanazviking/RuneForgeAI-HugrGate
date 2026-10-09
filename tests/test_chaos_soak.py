"""Slice 273 — long soak tests."""

from __future__ import annotations

import json

import pytest

from hugrgate.chaos import (
    ScheduledFault,
    SoakConfig,
    SoakReport,
    SoakRunner,
)
from hugrgate.chaos.backend_faults import FaultSpec, FaultyBackend
from hugrgate.core import HugrGate
from hugrgate.errors import BackendError, SpecError
from hugrgate.spec import DecisionSpec
from tests.conftest import StubBackend

pytestmark = pytest.mark.slow


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def test_soak_config_validation():
    with pytest.raises(SpecError):
        SoakConfig(duration_s=0)
    with pytest.raises(SpecError):
        SoakConfig(target_ops_per_s=-1)
    with pytest.raises(SpecError):
        SoakConfig(max_ops=0)
    with pytest.raises(SpecError):
        SoakConfig(invariant_every_n_ops=0)
    with pytest.raises(SpecError):
        ScheduledFault("f", at_s=2.0, until_s=1.0,
                       apply=lambda: None, revert=lambda: None)
    with pytest.raises(SpecError):
        ScheduledFault("", at_s=0.0, until_s=1.0,
                       apply=lambda: None, revert=lambda: None)
    with pytest.raises(SpecError):
        SoakRunner("not-callable")  # type: ignore[arg-type]


def test_soak_clean_run_passes():
    gate = HugrGate()
    gate.register(StubBackend(name="b", value="a"))
    accepted = []

    def workload(i):
        result = gate.decide({}, _spec(), backend_name="b")
        assert result.accepted
        accepted.append(result.value)

    def values_in_spec():
        assert set(accepted) <= {"a", "b"}, f"out-of-spec: {accepted!r}"

    runner = SoakRunner(workload, invariants=[values_in_spec])
    report = runner.run(SoakConfig(duration_s=1.0, target_ops_per_s=40.0))
    assert isinstance(report, SoakReport)
    assert report.passed is True
    assert report.ops_completed >= 20  # paced near the target rate
    assert report.errors == {}
    assert report.violations == []
    json.dumps(report.to_dict())


def test_soak_with_scheduled_fault_counts_expected_errors():
    gate = HugrGate()
    flaky = FaultyBackend(StubBackend(name="flaky", value="a"))
    gate.register(flaky)
    accepted = []

    def workload(i):
        result = gate.decide({}, _spec(), backend_name="flaky")
        accepted.append(result.value)

    def values_in_spec():
        assert set(accepted) <= {"a", "b"}

    def arm():
        flaky.arm(FaultSpec(mode="error_rate", rate=0.5, seed=7))

    def disarm():
        flaky.disarm("error_rate")

    runner = SoakRunner(
        workload,
        invariants=[values_in_spec],
        faults=[ScheduledFault("flap", at_s=0.3, until_s=1.2,
                               apply=arm, revert=disarm)])
    report = runner.run(SoakConfig(
        duration_s=2.0, target_ops_per_s=40.0,
        expected_errors=("BackendError",)))
    assert report.passed is True
    assert report.faults_applied == ["flap"]
    assert report.errors.get("BackendError", 0) > 0  # fault really fired
    assert report.unexpected_errors == {}
    assert report.violations == []
    assert flaky.armed_modes() == []  # fault reverted even mid-schedule


def test_soak_catches_invariant_violation():
    seen = []

    def workload(i):
        seen.append(i)

    def broken_invariant():
        raise AssertionError(f"counter went wrong at {len(seen)}")

    runner = SoakRunner(workload, invariants=[broken_invariant])
    report = runner.run(SoakConfig(duration_s=0.5, target_ops_per_s=40.0,
                                   invariant_every_n_ops=10))
    assert report.passed is False
    assert len(report.violations) > 0
    assert "counter went wrong" in report.violations[0]
    assert report.ops_completed > 0  # soak continued past violations


def test_soak_flags_unexpected_error_type():
    def workload(i):
        if i == 3:
            raise BackendError("expected flap")
        if i == 7:
            raise ValueError("nobody expected this")

    runner = SoakRunner(workload)
    report = runner.run(SoakConfig(duration_s=0.5, target_ops_per_s=40.0,
                                   expected_errors=("BackendError",)))
    assert report.passed is False
    assert report.errors == {"BackendError": 1, "ValueError": 1}
    assert report.unexpected_errors == {"ValueError": 1}


def test_soak_respects_max_ops():
    calls = {"n": 0}

    def workload(i):
        calls["n"] += 1

    runner = SoakRunner(workload)
    report = runner.run(SoakConfig(duration_s=60.0, target_ops_per_s=1000.0,
                                   max_ops=25))
    assert report.ops_completed == 25
    assert report.duration_s < 5.0  # stopped by max_ops, not the clock
    assert report.passed is True
