"""Slice 373 — CI quality gates.

Covers: EvalGateError registration (code/recoverable), gate
pass/fail math for every operator, wildcard vs named backends,
fail-closed behavior on unscored metrics and unknown backends,
assert_gates raising with failure details, RunRecord input,
gates_from_config, duplicate-name and bad-op validation, and
serialization round-trips.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import EvalError, EvalGateError
from hugrgate.evlab import (
    Gate,
    GateResult,
    GateSuite,
    assert_gates,
    check_gates,
    gates_from_config,
)
from hugrgate.evlab.api import RunRecord


def _results():
    return {
        "stub": {"accuracy": 0.92, "brier_score": 0.08},
        "other": {"accuracy": 0.70, "brier_score": 0.25},
    }


def _suite():
    return GateSuite(name="ci", gates=[
        Gate(name="acc-floor", metric="accuracy", op=">=", threshold=0.8),
        Gate(name="brier-cap", metric="brier_score", op="<=",
             threshold=0.2),
    ])


# --- error registration -------------------------------------------------------------------

def test_eval_gate_error_registered():
    assert EvalGateError.code == "eval_gate_error"
    assert EvalGateError.recoverable is False
    assert issubclass(EvalGateError, EvalError) is False


# --- gate math ----------------------------------------------------------------------------------

def test_check_gates_per_backend():
    outcomes = check_gates(_suite(), _results())
    assert len(outcomes) == 4
    by_key = {(o.gate, o.backend): o for o in outcomes}
    assert by_key[("acc-floor", "stub")].passed is True
    assert by_key[("acc-floor", "other")].passed is False
    assert by_key[("acc-floor", "other")].actual == pytest.approx(0.70)
    assert by_key[("brier-cap", "other")].passed is False
    assert "fails" in by_key[("brier-cap", "other")].detail


def test_operators():
    results = {"b": {"m": 0.5}}
    cases = [(">=", 0.5, True), (">=", 0.6, False), ("<=", 0.5, True),
             ("<=", 0.4, False), (">", 0.49, True), (">", 0.5, False),
             ("<", 0.51, True), ("<", 0.5, False), ("==", 0.5, True),
             ("==", 0.6, False)]
    for op, threshold, expected in cases:
        suite = GateSuite(name="s", gates=[
            Gate(name="g", metric="m", op=op, threshold=threshold)])
        (outcome,) = check_gates(suite, results)
        assert outcome.passed is expected, (op, threshold)


def test_named_backends():
    suite = GateSuite(name="s", gates=[
        Gate(name="g", metric="accuracy", op=">=", threshold=0.8,
             backends=("stub",))])
    outcomes = check_gates(suite, _results())
    assert [(o.backend, o.passed) for o in outcomes] == [("stub", True)]


def test_fail_closed_on_unscored_metric():
    suite = GateSuite(name="s", gates=[
        Gate(name="g", metric="auroc", op=">=", threshold=0.5)])
    outcomes = check_gates(suite, _results())
    assert len(outcomes) == 2
    assert all(o.passed is False for o in outcomes)
    assert all(o.actual is None for o in outcomes)
    assert all("not scored" in o.detail for o in outcomes)


def test_fail_closed_on_unknown_backend():
    suite = GateSuite(name="s", gates=[
        Gate(name="g", metric="accuracy", op=">=", threshold=0.5,
             backends=("ghost",))])
    (outcome,) = check_gates(suite, _results())
    assert outcome.passed is False
    assert outcome.actual is None


def test_bool_metric_not_scored():
    suite = GateSuite(name="s", gates=[
        Gate(name="g", metric="flag", op="==", threshold=1.0)])
    (outcome,) = check_gates(suite, {"b": {"flag": True}})
    assert outcome.passed is False  # bools are not numeric evidence


# --- assert path ------------------------------------------------------------------------------------

def test_assert_gates_passes_through():
    outcomes = assert_gates(_suite(), {"stub": {"accuracy": 0.9,
                                               "brier_score": 0.1}})
    assert all(o.passed for o in outcomes)


def test_assert_gates_raises_with_details():
    with pytest.raises(EvalGateError) as ei:
        assert_gates(_suite(), _results())
    message = str(ei.value)
    assert "acc-floor@other" in message
    assert "brier-cap@other" in message
    assert ei.value.details["suite"] == "ci"
    assert len(ei.value.details["failures"]) == 2


def test_assert_gates_accepts_run_record():
    record = RunRecord(
        run_id="r1", experiment_name="e", seed=0,
        started_at="2026-10-09T12:00:00",
        finished_at="2026-10-09T12:00:01", elapsed_s=1.0,
        hugrgate_version="0.1.0", python_version="3.12",
        platform={}, dataset_name="d", dataset_version="1",
        dataset_fingerprint="f", policy={}, privacy_class="open",
        tags={}, backends={"stub": {"accuracy": 0.95}}, n_items=5)
    suite = GateSuite(name="s", gates=[
        Gate(name="g", metric="accuracy", op=">=", threshold=0.9)])
    outcomes = assert_gates(suite, record)
    assert outcomes[0].backend == "stub" and outcomes[0].passed


# --- config + validation -------------------------------------------------------------------------------

def test_gates_from_config():
    suite = gates_from_config([
        {"name": "g1", "metric": "accuracy", "op": ">=",
         "threshold": 0.8, "backends": ["stub"]},
        {"name": "g2", "metric": "brier_score", "op": "<=",
         "threshold": 0.2},
    ], name="from-yaml")
    assert suite.name == "from-yaml"
    assert suite.gates[0].backends == ("stub",)
    assert suite.gates[1].backends == ("*",)


def test_gate_validation():
    with pytest.raises(EvalError):
        Gate(name="", metric="m", op=">=", threshold=0.5)
    with pytest.raises(EvalError):
        Gate(name="g", metric="", op=">=", threshold=0.5)
    with pytest.raises(EvalError):
        Gate(name="g", metric="m", op="!=", threshold=0.5)
    with pytest.raises(EvalError):
        Gate(name="g", metric="m", op=">=", threshold=0.5,
             backends=())
    with pytest.raises(EvalError):
        GateSuite(name="", gates=[])
    with pytest.raises(EvalError):
        GateSuite(name="s", gates=[
            Gate(name="dup", metric="m", op=">=", threshold=0.5),
            Gate(name="dup", metric="m", op=">=", threshold=0.5),
        ])


def test_serialization_roundtrip():
    suite = _suite()
    clone = GateSuite.from_dict(suite.to_dict())
    assert clone.to_dict() == suite.to_dict()
    (outcome,) = check_gates(
        GateSuite(name="s", gates=[
            Gate(name="g", metric="m", op=">=", threshold=0.5)]),
        {"b": {"m": 0.6}})
    d = outcome.to_dict()
    assert GateResult(**d).to_dict() == d
