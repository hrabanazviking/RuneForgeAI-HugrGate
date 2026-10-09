"""Slice 374 — Public report generator.

Covers: full report rendering (run/comparisons/gates/
regressions/repro/notes sections), graceful empty sections,
generic metric columns, bench_json embedding via bench_report,
write_lab_report round-trip + overwrite refusal, validation,
and LabReport serialization.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import EvalError
from hugrgate.evlab import (
    LabReport,
    lab_report_from_run,
    render_lab_markdown,
    write_lab_report,
)
from hugrgate.evlab.api import RunRecord


def _record():
    return RunRecord(
        run_id="r1", experiment_name="exp", seed=42,
        started_at="2026-10-09T12:00:00",
        finished_at="2026-10-09T12:05:00", elapsed_s=300.0,
        hugrgate_version="0.9.0", python_version="3.12.1",
        platform={"os": "linux"}, dataset_name="smoke",
        dataset_version="1.2.0", dataset_fingerprint="abc123",
        policy={"temperature": 0.0}, privacy_class="open",
        tags={},
        backends={
            "stub": {"accuracy": 0.92, "brier_score": 0.08,
                     "ece": 0.02, "custom_z": 1.5},
            "other": {"accuracy": 0.70, "brier_score": 0.25,
                      "ece": 0.10},
        },
        n_items=100, git_sha="deadbeef")


def _full_report():
    return lab_report_from_run(
        _record(),
        comparisons=[{
            "backend_a": "stub", "backend_b": "other",
            "metric": "accuracy", "estimate_a": 0.92,
            "estimate_b": 0.70, "diff_ci_low": 0.15,
            "diff_ci_high": 0.29, "p_value": 0.001,
            "wins_a": 90, "wins_b": 60, "ties": 10,
            "verdict": "a_better"}],
        gate_results=[
            {"gate": "acc-floor", "backend": "stub",
             "metric": "accuracy", "op": ">=", "threshold": 0.8,
             "actual": 0.92, "passed": True},
            {"gate": "acc-floor", "backend": "other",
             "metric": "accuracy", "op": ">=", "threshold": 0.8,
             "actual": 0.70, "passed": False}],
        regressions=[{
            "dataset": "smoke", "backend": "other",
            "metric": "accuracy", "current": 0.70,
            "baseline": 0.85, "drop": 0.15,
            "current_run_id": "r1", "baseline_run_id": "r0"}],
        repro={"dataset_name": "smoke", "dataset_version": "1.2.0",
               "dataset_fingerprint": "abc123",
               "backends": ["stub", "other"], "seed": 42,
               "hugrgate_version": "0.9.0",
               "python_version": "3.12.1", "git_sha": "deadbeef",
               "command": "pytest -q"},
        notes=["Smoke run for slice 374."])


# --- rendering -------------------------------------------------------------------------------------

def test_full_report_sections():
    text = render_lab_markdown(_full_report())
    assert text.startswith("# Evaluation report — smoke")
    for section in ("## Run", "### Metrics",
                    "## Head-to-head comparisons", "## Quality gates",
                    "## Regressions", "## Reproducibility",
                    "## Notes"):
        assert section in text
    assert "`smoke` v1.2.0" in text
    assert "| stub | 0.9200 | 0.0800 | 0.0200 | 1.5000 |" in text
    assert "**a_better**" in text
    assert "**FAIL**" in text and "**PASS**" in text
    assert "drop 0.1500" in text
    assert "pytest -q" in text
    assert "Smoke run for slice 374." in text


def test_metric_column_order():
    text = render_lab_markdown(_full_report())
    header = next(line for line in text.splitlines()
                  if line.startswith("| backend |"))
    cols = [c.strip() for c in header.split("|")[1:-1]]
    assert cols[0] == "backend"
    # Preferred metrics first, in canonical order; custom last.
    assert cols[1:4] == ["accuracy", "brier_score", "ece"]
    assert cols[-1] == "custom_z"


def test_empty_sections_render_explicitly():
    text = render_lab_markdown(lab_report_from_run(_record()))
    assert "No comparisons evaluated." in text
    assert "No gates evaluated." in text
    assert "No regressions detected." in text
    assert "No reproducibility manifest attached." in text


def test_no_run_record():
    report = LabReport(title="Orphan")
    text = render_lab_markdown(report)
    assert "No run record attached." in text


def test_bench_json_embedded():
    bench_json = {
        "dataset": "smoke",
        "hugrgate_version": "0.9.0",
        "platform": {"os": "linux"},
        "backends": {
            "stub": {
                "n_decided": 100, "n_abstained": 0,
                "abstention_rate": 0.0, "n_errors": 0,
                "accuracy": 0.92, "brier_score": 0.08, "ece": 0.02,
                "latency_p50_ms": 1.2, "latency_p99_ms": 2.5,
                "latency_mean_ms": 1.4, "throughput_per_s": 700.0,
                "calibration": {},
                "reliability_bins": [
                    {"bin_low": 0.0, "bin_high": 1.0, "count": 100,
                     "accuracy": 0.92, "avg_confidence": 0.95}],
            }
        },
    }
    report = lab_report_from_run(_record(), bench_json=bench_json)
    text = render_lab_markdown(report)
    assert "## Benchmark detail" in text
    assert "# HugrGate benchmark report — smoke" in text
    assert "Reliability diagram" in text


def test_render_rejects_wrong_type():
    with pytest.raises(EvalError):
        render_lab_markdown({"title": "x"})


def test_from_run_rejects_wrong_type():
    with pytest.raises(EvalError):
        lab_report_from_run({"run_id": "x"})


# --- writing ------------------------------------------------------------------------------------------

def test_write_and_read_back(tmp_path):
    report = _full_report()
    path = write_lab_report(report, tmp_path / "r" / "report.md")
    assert path.endswith("report.md")
    text = (tmp_path / "r" / "report.md").read_text(encoding="utf-8")
    assert text == render_lab_markdown(report)


def test_write_refuses_overwrite(tmp_path):
    target = tmp_path / "report.md"
    target.write_text("existing")
    with pytest.raises(EvalError):
        write_lab_report(_full_report(), target)


# --- serialization ---------------------------------------------------------------------------------------

def test_lab_report_roundtrip():
    report = _full_report()
    clone = LabReport.from_dict(report.to_dict())
    assert clone.to_dict() == report.to_dict()
    assert render_lab_markdown(clone) == render_lab_markdown(report)
