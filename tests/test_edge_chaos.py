"""Slice 199 — edge failure testing tests."""

from __future__ import annotations

import json

import pytest

from hugrgate.edge.chaos import (
    BUILTIN_SCENARIOS,
    ChaosError,
    ChaosResult,
    ChaosRunner,
    FaultScenario,
    build_builtin_runner,
    run_builtin_scenarios,
)

# --- runner mechanics -----------------------------------------------------------------------

def test_runner_executes_and_reports():
    runner = ChaosRunner()
    runner.register(FaultScenario("ok", "passes", lambda: None))
    def boom() -> None:
        raise RuntimeError("injected")
    runner.register(FaultScenario("bad", "fails", boom))
    results = runner.run_all()
    assert [(r.name, r.passed) for r in results] == \
        [("bad", False), ("ok", True)]  # sorted by name
    report = runner.report()
    assert report["scenarios"] == 2
    assert report["passed"] == 1
    assert report["failed"] == ["bad"]
    assert report["all_passed"] is False
    assert "RuntimeError: injected" in results[0].detail
    json.dumps(report)


def test_runner_continues_past_failures():
    calls: list[str] = []
    runner = ChaosRunner()
    def boom() -> None:
        calls.append("bad")
        raise ValueError("x")
    runner.register(FaultScenario("bad", "fails", boom))
    runner.register(FaultScenario(
        "after", "runs anyway", lambda: calls.append("after")))
    runner.run_all()
    assert calls == ["after", "bad"] or calls == ["bad", "after"]
    assert len(runner.report()["results"]) == 2


def test_runner_rejects_duplicates_and_non_scenarios():
    runner = ChaosRunner()
    runner.register(FaultScenario("s", "d", lambda: None))
    with pytest.raises(ChaosError, match="duplicate"):
        runner.register(FaultScenario("s", "d", lambda: None))
    with pytest.raises(ChaosError, match="can only register"):
        runner.register("nope")  # type: ignore[arg-type]
    with pytest.raises(ChaosError, match="non-empty"):
        FaultScenario("  ", "d", lambda: None)
    assert runner.scenarios() == ["s"]


def test_result_serializes():
    r = ChaosResult("s", True, "")
    assert r.to_dict() == {"name": "s", "passed": True, "detail": ""}


# --- built-in scenarios --------------------------------------------------------------------------

def test_builtin_scenarios_all_pass():
    report = run_builtin_scenarios()
    assert report["all_passed"] is True, report
    assert report["scenarios"] == 6
    assert report["failed"] == []


def test_builtin_scenario_names_stable():
    names = [s.name for s in BUILTIN_SCENARIOS]
    assert names == ["power-loss-mid-write", "thermal-spike", "npu-dropout",
                     "memory-pressure", "flash-budget-exhaustion",
                     "watchdog-starvation"]
    runner = build_builtin_runner()
    assert runner.scenarios() == sorted(names)
