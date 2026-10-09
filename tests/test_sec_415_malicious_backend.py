"""Slice 415 — malicious backend tests.

Five hostile backends (lying, exfiltrating, hanging, giant
output, exploding) are each contained by a real layer; the
control backend decides normally.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import (
    BackendError,
    InputTooLarge,
    SandboxViolation,
    SpecError,
    TimeoutError,
)
from hugrgate.security.malicious_backend import (
    ExfiltratingBackend,
    ExplodingBackend,
    GiantOutputBackend,
    HangingBackend,
    LyingBackend,
    check_result_size,
    run_gauntlet,
)
from hugrgate.security.sandbox import SandboxedBackend, SandboxPolicy
from hugrgate.spec import DecisionSpec
from hugrgate.timeout import TimeoutBackend
from hugrgate.validation import validate_result


def _spec() -> DecisionSpec:
    return DecisionSpec(type="categorical", options=["yes", "no"])


def test_gauntlet_passes():
    report = run_gauntlet()
    assert report.escaped == []
    assert report.control_ok
    assert report.passed
    assert set(report.contained) == {
        "lying", "exfiltrating", "hanging", "giant_output", "exploding",
    }
    assert report.to_dict()["passed"] is True


def test_lying_rejected_by_validation():
    with pytest.raises(SpecError):
        validate_result(LyingBackend().evaluate({"x": 1}, _spec()), _spec())


def test_exfiltrating_blocked_before_socket():
    with pytest.raises(SandboxViolation):
        SandboxedBackend(ExfiltratingBackend(),
                         SandboxPolicy()).evaluate({"x": 1}, _spec())


def test_hanging_hits_deadline():
    with pytest.raises(TimeoutError):
        TimeoutBackend(HangingBackend(),
                       explicit_deadline_ms=200).evaluate({"x": 1}, _spec())


def test_giant_output_rejected():
    with pytest.raises(InputTooLarge):
        check_result_size(
            GiantOutputBackend().evaluate({"x": 1}, _spec()), max_bytes=64)


def test_exploding_becomes_backend_error():
    from hugrgate import DecisionPolicy, HugrGate
    gate = HugrGate()
    gate.register(ExplodingBackend())
    with pytest.raises(BackendError):
        gate.decide({"x": 1}, _spec(), DecisionPolicy(),
                    backend_name="exploding")


def test_result_size_boundary():
    from hugrgate.result import DecisionResult
    ok = DecisionResult(value="yes", probability=0.5, backend="t",
                        model="t", metadata={"k": "v"})
    assert check_result_size(ok, max_bytes=10_000) > 0
