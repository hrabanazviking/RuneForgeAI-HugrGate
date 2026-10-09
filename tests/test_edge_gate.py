"""Slice 200 — edge release gate tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hugrgate.edge.gate import (
    GATE_CHECKS,
    GateCheck,
    GateError,
    GateReport,
    edge_release_gate,
)


def _skeleton(root: Path) -> None:
    """Minimal repo skeleton the fast gate checks run against."""
    (root / "hugrgate" / "edge").mkdir(parents=True)
    (root / "hugrgate" / "edge" / "clean.py").write_text(
        '"""Clean module."""\n__all__ = ["x"]\nx = 1\n')
    docs = root / "docs" / "campaign-viii"
    docs.mkdir(parents=True)
    for n in range(176, 201):
        (docs / f"{n}-slice.md").write_text("# doc\n" + "x" * 500)
    bench = root / "benchmarks" / "edge"
    bench.mkdir(parents=True)
    (bench / "a.json").write_text(json.dumps({
        "schema": "edge-bench/1", "cases": {"c": {"mean_s": 0.1}}}))


# --- report mechanics -----------------------------------------------------------------

def test_gate_report_summary_and_serialization():
    report = GateReport(
        checks=[GateCheck("a", True, "ok"), GateCheck("b", False, "bad")],
        blockers=["[b] bad"])
    assert not report.passed
    assert "FAIL" in report.summary()
    assert "1/2" in report.summary()
    json.dumps(report.to_dict())
    good = GateReport(checks=[GateCheck("a", True)])
    assert good.passed and "PASS" in good.summary()


def test_unknown_check_name_rejected(tmp_path: Path):
    with pytest.raises(GateError, match="unknown gate checks"):
        edge_release_gate(tmp_path, only=["nope"])


# --- fast checks against a fixture skeleton ----------------------------------------------

FAST = ["slice-docs", "benchmark-artifacts", "stub-scan"]


def test_fast_checks_pass_on_skeleton(tmp_path: Path):
    _skeleton(tmp_path)
    report = edge_release_gate(tmp_path, only=list(FAST))
    assert report.passed, report.to_dict()
    assert [c.name for c in report.checks] == list(FAST)


def test_slice_docs_missing_and_trivial(tmp_path: Path):
    _skeleton(tmp_path)
    (tmp_path / "docs" / "campaign-viii" / "176-slice.md").unlink()
    (tmp_path / "docs" / "campaign-viii" / "177-slice.md").write_text("tiny")
    report = edge_release_gate(tmp_path, only=["slice-docs"])
    assert not report.passed
    assert "176" in report.blockers[0]
    report2 = edge_release_gate(tmp_path, only=["slice-docs"])
    assert "trivial" in report2.blockers[0] or "176" in report2.blockers[0]


def test_stub_scan_catches_markers(tmp_path: Path):
    _skeleton(tmp_path)
    (tmp_path / "hugrgate" / "edge" / "dirty.py").write_text(
        "# TODO: finish this\n__all__ = []\n")
    report = edge_release_gate(tmp_path, only=["stub-scan"])
    assert not report.passed
    assert "dirty.py" in report.blockers[0]


def test_benchmark_artifacts_validated(tmp_path: Path):
    _skeleton(tmp_path)
    (tmp_path / "benchmarks" / "edge" / "bad.json").write_text(
        '{"schema": "nope"}')
    report = edge_release_gate(tmp_path, only=["benchmark-artifacts"])
    assert not report.passed
    assert "bad.json" in report.blockers[0]


def test_chaos_check_runs_real_scenarios(tmp_path: Path):
    report = edge_release_gate(tmp_path, only=["chaos"])
    assert report.passed, report.to_dict()
    assert "6/6" in report.checks[0].detail


def test_gate_check_order_matches_gate_checks():
    assert tuple(GATE_CHECKS) == ("test-suite", "ruff", "mypy", "chaos",
                                 "slice-docs", "benchmark-artifacts",
                                 "stub-scan", "maps-fresh")
