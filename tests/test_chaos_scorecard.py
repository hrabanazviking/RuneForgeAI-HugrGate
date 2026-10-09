"""Slice 274 — reliability scorecard tests."""

from __future__ import annotations

import json

import pytest

from hugrgate.chaos import (
    CrashReport,
    DegradationReport,
    RecoveryReport,
    Scorecard,
    ScorecardEntry,
    ScorecardReport,
    SoakReport,
    builtin_degradation_plans,
    dependency_failure_matrix,
)
from hugrgate.chaos.framework import (
    ExperimentReport,
    FaultResult,
    ProbeOutcome,
)
from hugrgate.errors import SpecError


def _passing_experiment_report(name="exp-1"):
    return ExperimentReport(
        experiment=name, hypothesis="h", target="chaos-lab",
        seed=7, dry_run=True,
        steady_before={"p": ProbeOutcome(ok=True)},
        steady_after={"p": ProbeOutcome(ok=True)},
        faults=[FaultResult(name="f", injected=True, verified=True,
                             rolled_back=True)])


def _failing_experiment_report(name="exp-2"):
    report = _passing_experiment_report(name)
    report.steady_after = {"p": ProbeOutcome(ok=False, detail="broke")}
    return report


# --- entries and grading -----------------------------------------------------------------------------------------

def test_entry_validation():
    with pytest.raises(SpecError, match="non-empty"):
        ScorecardEntry("", "c", True)
    with pytest.raises(SpecError, match="non-empty"):
        ScorecardEntry("n", "", True)
    with pytest.raises(SpecError, match="positive"):
        ScorecardEntry("n", "c", True, weight=0)
    with pytest.raises(SpecError, match="can only add"):
        Scorecard().add("nope")  # type: ignore[arg-type]
    card = Scorecard()
    card.add(ScorecardEntry("a", "c", True))
    with pytest.raises(SpecError, match="duplicate"):
        card.add(ScorecardEntry("a", "c", True))
    with pytest.raises(SpecError, match="empty"):
        Scorecard().build()
    with pytest.raises(SpecError, match="threshold"):
        Scorecard(threshold=0)
    with pytest.raises(SpecError, match="non-empty"):
        Scorecard(title=" ")


def test_all_passing_scorecard():
    card = Scorecard("campaign-xi")
    card.add_experiment(_passing_experiment_report())
    card.add_dependency_matrix(dependency_failure_matrix())
    report = builtin_degradation_plans().execute(
        "serve-stale-cache", failure_code="timeout")
    card.add_degradation(report)
    built = card.build()
    assert isinstance(built, ScorecardReport)
    assert built.verdict == "PASS"
    assert built.score == 1.0
    assert built.grade == "A"
    assert built.failed == []
    assert built.waived == []
    d = built.to_dict()
    json.dumps(d)
    text = built.render()
    assert "verdict: PASS" in text
    assert "serve-stale-cache" in text


def test_failing_entry_flunks_the_card():
    card = Scorecard()
    card.add_experiment(_passing_experiment_report("exp-1"))
    card.add_experiment(_failing_experiment_report("exp-2"), weight=3.0)
    built = card.build()
    assert built.verdict == "FAIL"
    assert built.score == pytest.approx(0.25)  # 1 of 4 weighted
    assert built.grade == "F"
    assert built.failed == ["experiment:exp-2"]
    assert "FAIL" in built.render()


def test_waiver_is_explicit_and_auditable():
    card = Scorecard()
    card.add_experiment(_failing_experiment_report())
    with pytest.raises(SpecError, match="unknown"):
        card.waive("ghost", "reason")
    with pytest.raises(SpecError, match="non-empty"):
        card.waive("experiment:exp-2", "  ")
    card.waive("experiment:exp-2", "known flake, tracked in #42")
    built = card.build()
    assert built.verdict == "PASS"
    assert built.waived == ["experiment:exp-2"]
    d = built.to_dict()
    entry = d["entries"][0]
    assert entry["waived"] is True
    assert entry["waiver_reason"] == "known flake, tracked in #42"
    assert entry["passed"] is False  # waiver doesn't rewrite history
    assert "WAIVED" in built.render()
    with pytest.raises(SpecError, match="already waived"):
        card.waive("experiment:exp-2", "again")


def test_grade_bands_and_threshold():
    def card_with(score_entries):
        card = Scorecard(threshold=0.8)
        for i, passed in enumerate(score_entries):
            card.add(ScorecardEntry(f"e{i}", "c", passed))
        return card.build()
    assert card_with([True] * 19 + [False]).grade == "A"      # 0.95
    assert card_with([True] * 17 + [False] * 3).grade == "B"  # 0.85
    assert card_with([True] * 7 + [False] * 3).grade == "C"   # 0.70
    assert card_with([True, False]).grade == "D"              # 0.50
    assert card_with([False]).grade == "F"
    assert card_with([True] * 4 + [False]).verdict == "PASS"  # 0.8 >= 0.8
    assert card_with([True] * 3 + [False] * 2).verdict == "FAIL"  # 0.6


# --- adapters for every report shape --------------------------------------------------------------------------------

def test_adapters_cover_all_report_shapes():
    card = Scorecard()
    card.add_experiment(_passing_experiment_report())
    card.add_dependency_matrix({"all_survived": True, "survived": 2,
                                "scenarios": 2, "failed": []},
                               name="dependency-matrix:pass")
    card.add_dependency_matrix({"all_survived": False, "survived": 1,
                                "scenarios": 2, "failed": ["x"]},
                               name="dependency-matrix:fail")
    deg = DegradationReport(plan_name="p", failure_code="f", steps=[],
                            started_at=0.0, finished_at=0.1)
    card.add_degradation(deg)  # no steps applied -> not graceful
    rec = RecoveryReport(verifier_name="v", probes=[], started_at=0.0,
                         finished_at=0.1)
    card.add_recovery(rec)  # no probes -> not recovered
    soak = SoakReport(ops_completed=10, errors={}, unexpected_errors={},
                      violations=[], faults_applied=[], duration_s=1.0)
    card.add_soak(soak)
    crash = CrashReport(pid=1, killed=True, checkpoints_valid=3,
                        recovered_counter=42, torn_tmp_files=1,
                        duration_s=1.0)
    card.add_crash(crash)
    built = card.build()
    assert built.verdict == "FAIL"
    assert set(built.failed) == {"dependency-matrix:fail",
                                 "degradation:p", "recovery:v"}
    cats = {e["category"] for e in built.to_dict()["entries"]}
    assert cats == {"chaos-experiments", "dependencies", "degradation",
                    "recovery", "soak"}
    text = built.render()
    for name in ("experiment:exp-1", "dependency-matrix:pass",
                 "dependency-matrix:fail", "degradation:p",
                 "recovery:v", "soak", "crash-only-restart"):
        assert name in text
