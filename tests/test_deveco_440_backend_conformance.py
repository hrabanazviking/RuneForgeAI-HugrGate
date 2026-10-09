"""Slice 440 — backend conformance kit.

The built-in backends must pass their own battery; deliberately
broken backends must fail with named checks. ``assert_conformance``
raises the taxonomy error.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from hugrgate.backend import Backend
from hugrgate.conformance import (
    assert_conformance,
    run_backend_conformance,
)
from hugrgate.errors import ConformanceError
from hugrgate.result import DecisionResult
from hugrgate.server import UniformBackend, build_gate


class SkewedBackend(Backend):
    """Distribution does not sum to 1."""
    name = "skewed"

    def capabilities(self):
        return {}

    def supports(self, spec):
        return True

    def evaluate(self, state, spec, context=None):
        return DecisionResult(value="a", probability=0.5,
                              distribution={"a": 0.5, "b": 0.2},
                              uncertainty=0.0, accepted=True,
                              backend=self.name, model="x",
                              latency_ms=0.1,
                              calibration_profile="none",
                              fallback_used=False, metadata={})


class RawRaiseBackend(Backend):
    """Raises a raw Exception on bad input (taxonomy violation)."""
    name = "rawraise"

    def capabilities(self):
        return {}

    def supports(self, spec):
        return True

    def evaluate(self, state, spec, context=None):
        if not isinstance(state, Mapping):
            raise RuntimeError("boom")  # not taxonomy, not stdlib-validation
        return DecisionResult(value="a", probability=1.0,
                              distribution={"a": 1.0}, uncertainty=0.0,
                              accepted=True, backend=self.name,
                              model="x", latency_ms=0.1,
                              calibration_profile="none",
                              fallback_used=False, metadata={})


class OutsideSpaceBackend(Backend):
    """Decides a value outside the spec's value space."""
    name = "outside"

    def capabilities(self):
        return {}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        return DecisionResult(value="zzz", probability=1.0,
                              distribution={"zzz": 1.0}, uncertainty=0.0,
                              accepted=True, backend=self.name,
                              model="x", latency_ms=0.1,
                              calibration_profile="none",
                              fallback_used=False, metadata={})


def test_uniform_backend_is_conformant():
    report = run_backend_conformance(UniformBackend())
    assert report.passed, [c for c in report.failures]
    assert len(report.checks) >= 8


def test_builtin_backends_are_conformant():
    gate = build_gate()
    for name in gate.registry.list():
        backend = gate.registry.get(name)
        report = run_backend_conformance(backend)
        assert report.passed, (name, [c for c in report.failures])


def test_skewed_distribution_fails():
    report = run_backend_conformance(SkewedBackend())
    assert not report.passed
    names = [c.name for c in report.failures]
    assert any(n.startswith("evaluate[") for n in names)
    # DecisionResult validates at construction, so the skewed
    # distribution surfaces as a SpecError on the valid input —
    # still a conformance failure, with the cause in the detail.
    assert any("sum to 1" in c.detail for c in report.failures)


def test_raw_exception_fails_taxonomy_check():
    report = run_backend_conformance(RawRaiseBackend())
    assert not report.passed
    assert "error-taxonomy" in [c.name for c in report.failures]


def test_value_outside_spec_space_fails():
    report = run_backend_conformance(OutsideSpaceBackend())
    assert not report.passed
    assert any("outside spec value space" in c.detail
               for c in report.failures)


def test_assert_conformance_raises_taxonomy_error():
    report = run_backend_conformance(SkewedBackend())
    with pytest.raises(ConformanceError) as exc:
        assert_conformance(report)
    assert exc.value.code == "conformance_error"
    assert exc.value.recoverable is False
    assert "skewed" in exc.value.message


def test_assert_conformance_passes_silently():
    assert_conformance(run_backend_conformance(UniformBackend()))


def test_report_is_json_serializable():
    report = run_backend_conformance(SkewedBackend())
    data = report.to_dict()
    json.dumps(data)
    assert data["backend"] == "skewed"
    assert data["passed"] is False
    assert all("name" in c and "passed" in c for c in data["checks"])


def test_cli_check_backend_conformant(capsys):
    from hugrgate.cli import main
    assert main(["check-backend", "uniform"]) == 0
    out = capsys.readouterr().out
    assert "is conformant" in out


def test_cli_check_backend_table(capsys):
    from hugrgate.cli import main
    assert main(["--format", "table", "check-backend",
                 "uniform"]) == 0
    out = capsys.readouterr().out
    assert "check" in out.splitlines()[0]


def test_cli_check_backend_unknown_is_exit_2(capsys):
    from hugrgate.cli import main
    assert main(["check-backend", "no-such-backend"]) == 2
    assert "hugrgate:" in capsys.readouterr().err
