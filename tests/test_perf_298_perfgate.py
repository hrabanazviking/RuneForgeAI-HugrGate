"""Slice 298 — performance regression gates.

Covers: gate registration validation, median-of-samples measurement,
lower-better and higher-better regression math, pass/fail evaluation,
check() raising PerfGateError (non-recoverable) with breach detail,
missing-baseline and direction-change errors, record/evaluate
round-trip on a temp baseline, and the real default gates passing
against the committed artifact.
"""

from __future__ import annotations

import json

import pytest

from hugrgate.errors import PerfGateError
from hugrgate.perfgate import PerfGate, _regression_frac, default_gates


def _gate_at(tmp_path, gates):
    bp = tmp_path / "baseline.json"
    bp.write_text(json.dumps({"gates": gates}))
    return PerfGate(baseline_path=bp)


# --- math -----------------------------------------------------------------------------------


def test_regression_frac_lower_better():
    assert _regression_frac("lower-better", 100.0, 110.0) == pytest.approx(0.10)
    assert _regression_frac("lower-better", 100.0, 90.0) == pytest.approx(-0.10)
    assert _regression_frac("lower-better", 100.0, 100.0) == 0.0


def test_regression_frac_higher_better():
    assert _regression_frac("higher-better", 100.0, 90.0) == pytest.approx(0.10)
    assert _regression_frac("higher-better", 100.0, 110.0) == pytest.approx(-0.10)


def test_regression_frac_zero_baseline():
    assert _regression_frac("lower-better", 0.0, 0.0) == 0.0
    assert _regression_frac("lower-better", 0.0, 5.0) == float("inf")


# --- registration ----------------------------------------------------------------------------


def test_add_gate_validation(tmp_path):
    gate = PerfGate(baseline_path=tmp_path / "b.json")
    with pytest.raises(PerfGateError, match="non-empty"):
        gate.add_gate("", lambda: 1.0)
    with pytest.raises(PerfGateError, match="direction"):
        gate.add_gate("x", lambda: 1.0, direction="sideways")
    with pytest.raises(PerfGateError, match="max_regression_frac"):
        gate.add_gate("x", lambda: 1.0, max_regression_frac=0)
    with pytest.raises(PerfGateError, match="samples"):
        gate.add_gate("x", lambda: 1.0, samples=0)
    with pytest.raises(PerfGateError, match="callable"):
        gate.add_gate("x", "not-fn")
    gate.add_gate("x", lambda: 1.0)
    with pytest.raises(PerfGateError, match="already registered"):
        gate.add_gate("x", lambda: 1.0)


# --- evaluation -------------------------------------------------------------------------------


def _base(value, direction="lower-better", samples=3):
    return {"value": value, "direction": direction, "samples": samples,
            "unit": "us"}


def test_pass_within_tolerance(tmp_path):
    gate = _gate_at(tmp_path, {"g": _base(100.0)})
    gate.add_gate("g", lambda: 105.0, max_regression_frac=0.10, samples=3)
    (result,) = gate.check()
    assert result.passed is True
    assert result.regression_frac == pytest.approx(0.05)


def test_breach_raises_non_recoverable(tmp_path):
    gate = _gate_at(tmp_path, {"g": _base(100.0)})
    gate.add_gate("g", lambda: 200.0, max_regression_frac=0.10, samples=3)
    with pytest.raises(PerfGateError, match="breached") as ei:
        gate.check()
    assert "g:" in str(ei.value)
    assert "+100.0%" in str(ei.value)
    assert PerfGateError.recoverable is False


def test_higher_better_breach(tmp_path):
    gate = _gate_at(tmp_path, {"t": _base(1000.0, "higher-better")})
    gate.add_gate("t", lambda: 500.0, direction="higher-better",
                  max_regression_frac=0.10, samples=2)
    with pytest.raises(PerfGateError, match="breached"):
        gate.check()


def test_improvement_passes(tmp_path):
    gate = _gate_at(tmp_path, {"g": _base(100.0)})
    gate.add_gate("g", lambda: 50.0, samples=2)
    assert gate.check()[0].passed is True


def test_missing_baseline_file(tmp_path):
    gate = PerfGate(baseline_path=tmp_path / "nope.json")
    gate.add_gate("g", lambda: 1.0)
    with pytest.raises(PerfGateError, match="baseline artifact missing"):
        gate.evaluate()


def test_gate_without_baseline_entry(tmp_path):
    gate = _gate_at(tmp_path, {"other": _base(1.0)})
    gate.add_gate("g", lambda: 1.0, samples=1)
    with pytest.raises(PerfGateError, match="no baseline"):
        gate.evaluate()


def test_direction_change_requires_rebaseline(tmp_path):
    gate = _gate_at(tmp_path, {"g": _base(100.0, "lower-better")})
    gate.add_gate("g", lambda: 100.0, direction="higher-better", samples=1)
    with pytest.raises(PerfGateError, match="direction changed"):
        gate.evaluate()


def test_metric_exception_wrapped(tmp_path):
    def bad():
        raise RuntimeError("metric exploded")

    gate = _gate_at(tmp_path, {"g": _base(1.0)})
    gate.add_gate("g", bad, samples=1)
    with pytest.raises(PerfGateError, match=r"metric_fn.*RuntimeError"):
        gate.evaluate()


def test_record_baseline_round_trip(tmp_path):
    bp = tmp_path / "new.json"
    gate = PerfGate(baseline_path=bp)
    gate.add_gate("g", lambda: 42.0, direction="higher-better",
                  samples=3, unit="ops")
    gate.record_baseline()
    data = json.loads(bp.read_text())
    assert data["gates"]["g"]["value"] == 42.0
    assert data["gates"]["g"]["direction"] == "higher-better"
    # And the fresh baseline passes.
    assert gate.check()[0].passed is True


def test_median_resists_outliers(tmp_path):
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        return 10000.0 if calls["n"] == 2 else 100.0

    gate = _gate_at(tmp_path, {"g": _base(100.0)})
    gate.add_gate("g", flaky, max_regression_frac=0.10, samples=5)
    assert gate.check()[0].passed is True  # median ignores the spike


# --- committed artifact -------------------------------------------------------------------------

def test_default_gates_against_committed_baseline():
    gate = PerfGate()  # benchmarks/perf_baseline.json
    names = [n for n, _, _ in default_gates()]
    assert names == ["cache.key_us", "cache.get_hit_us"]
    for name, fn, kw in default_gates():
        gate.add_gate(name, fn, **kw)
    results = gate.check()
    assert all(r.passed for r in results)
    for r in results:
        assert r.baseline > 0 and r.measured > 0
