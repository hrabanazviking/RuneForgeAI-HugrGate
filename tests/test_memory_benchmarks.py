"""Slice 324 — Memory benchmark suite: structure, round-trip, comparison."""

from __future__ import annotations

import json

import pytest

from hugrgate.memory.benchmarks import (
    compare_reports,
    load_artifact,
    run_memory_benchmarks,
    save_artifact,
)


def test_report_structure():
    report = run_memory_benchmarks(n_episodes=50, n_queries=10,
                                   n_recalls=5, seed=324)
    assert report["slice"] == 324
    assert report["seed"] == 324
    assert report["workload"] == {"n_episodes": 50, "n_queries": 10,
                                  "n_recalls": 5}
    assert report["episodes_retained"] == 50
    assert report["memory_bytes"] > 0
    expected_ops = {"record_us", "attach_outcome_us", "find_us",
                    "recall_us", "export_import_us", "estimate_bytes_us"}
    assert set(report["summary"]) == expected_ops
    for op, stats in report["summary"].items():
        assert stats["n"] > 0, op
        assert stats["mean_us"] > 0, op
        assert stats["min_us"] <= stats["p50_us"] <= stats["p95_us"], op
        assert stats["p95_us"] <= stats["max_us"], op


def test_reproducible_seed():
    first = run_memory_benchmarks(n_episodes=50, n_queries=10,
                                  n_recalls=5, seed=7)
    second = run_memory_benchmarks(n_episodes=50, n_queries=10,
                                   n_recalls=5, seed=7)
    assert first["workload"] == second["workload"]
    assert first["episodes_retained"] == second["episodes_retained"]
    # timestamps serialize with full precision: allow a sliver
    assert abs(first["memory_bytes"]
               - second["memory_bytes"]) < 1000


def test_save_load_roundtrip(tmp_path):
    report = run_memory_benchmarks(n_episodes=20, n_queries=5,
                                   n_recalls=3, seed=1)
    path = tmp_path / "bench.json"
    saved = save_artifact(report, path)
    assert saved == path
    loaded = load_artifact(path)
    assert loaded == report


def test_load_rejects_bad_artifacts(tmp_path):
    with pytest.raises(ValueError):
        load_artifact(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_artifact(bad)
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"hello": 1}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_artifact(wrong)


def test_compare_self_is_identity():
    report = run_memory_benchmarks(n_episodes=20, n_queries=5,
                                   n_recalls=3, seed=1)
    comparison = compare_reports(report, report)
    assert comparison["workloads_match"] is True
    for op, ratio in comparison["ratios"].items():
        assert ratio == pytest.approx(1.0), op


def test_compare_flags_workload_mismatch():
    small = run_memory_benchmarks(n_episodes=20, n_queries=5,
                                  n_recalls=3, seed=1)
    big = run_memory_benchmarks(n_episodes=40, n_queries=5,
                                n_recalls=3, seed=1)
    comparison = compare_reports(small, big)
    assert comparison["workloads_match"] is False
    assert set(comparison["ratios"]) == set(small["summary"])


def test_workload_validation():
    with pytest.raises(ValueError):
        run_memory_benchmarks(n_episodes=0)
    with pytest.raises(ValueError):
        run_memory_benchmarks(n_queries=0)


def test_cli_compare_does_not_overwrite_baseline(tmp_path, capsys):
    from hugrgate.memory.benchmarks import main
    baseline_path = tmp_path / "baseline.json"
    report = run_memory_benchmarks(n_episodes=20, n_queries=5,
                                   n_recalls=3, seed=1)
    save_artifact(report, baseline_path)
    before = baseline_path.read_text(encoding="utf-8")
    rc = main(["--episodes", "20", "--queries", "5", "--recalls", "3",
               "--seed", "2", "--out", str(baseline_path), "--compare"])
    assert rc == 0
    assert baseline_path.read_text(encoding="utf-8") == before
    out = capsys.readouterr().out
    assert "ratios" in out
