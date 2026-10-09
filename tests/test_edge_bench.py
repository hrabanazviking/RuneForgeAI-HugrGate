"""Slice 196 — edge benchmark harness tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hugrgate.edge.bench import (
    ARTIFACT_SCHEMA,
    BenchmarkCase,
    BenchmarkError,
    EdgeBenchmark,
    compare_artifacts,
    edge_bench_suite,
    load_artifact,
)
from hugrgate.edge.platform import PlatformInfo


def _info(**over) -> PlatformInfo:
    base = {"arch": "x86_64", "system": "Linux", "release": "6.6",
            "python_version": (3, 11, 0),
            "python_implementation": "CPython", "cpu_count": 8,
            "cpu_features": (), "page_size": 4096, "byteorder": "little",
            "is_64bit": True, "live": False}
    base.update(over)
    return PlatformInfo(**base)  # type: ignore[arg-type]


# --- harness ------------------------------------------------------------------------

def test_run_measures_cases():
    ticks = [0.0]
    bench = EdgeBenchmark("t", platform=_info(),
                          timer=lambda: ticks[0])
    bench.add("fast", lambda: ticks.__setitem__(0, ticks[0] + 0.001),
              iterations=10, warmup=2)
    results = bench.run()
    assert set(results) == {"fast"}
    r = results["fast"]
    assert r.iterations == 10
    assert r.mean_s == pytest.approx(0.001)
    assert r.p50_s == pytest.approx(0.001)
    assert r.ops_per_s == pytest.approx(1000.0)
    assert r.min_s <= r.p50_s <= r.p99_s <= r.max_s


def test_duplicate_case_rejected():
    bench = EdgeBenchmark("t", platform=_info())
    bench.add("a", lambda: None)
    with pytest.raises(BenchmarkError, match="duplicate"):
        bench.add("a", lambda: None)


def test_bad_case_rejected():
    with pytest.raises(BenchmarkError, match="non-empty"):
        BenchmarkCase("", lambda: None)
    with pytest.raises(BenchmarkError, match="iterations"):
        BenchmarkCase("a", lambda: None, iterations=0)
    with pytest.raises(BenchmarkError, match="benchmark name"):
        EdgeBenchmark("  ", platform=_info())


def test_artifact_requires_run():
    bench = EdgeBenchmark("t", platform=_info())
    with pytest.raises(BenchmarkError, match="no results"):
        bench.artifact()


def test_artifact_roundtrip_and_surrogate_note(tmp_path: Path):
    from hugrgate.edge.platform import pi_baseline
    bench = EdgeBenchmark("t", platform=_info(),
                          baseline_board=pi_baseline("Raspberry Pi 5"))
    bench.add("a", lambda: None, iterations=5)
    bench.run()
    path = bench.save(tmp_path / "artifacts" / "bench.json")
    assert path.exists()
    data = load_artifact(path)
    assert data["schema"] == ARTIFACT_SCHEMA
    assert "SURROGATE HOST" in data["hardware_note"]
    assert "NEEDS_HARDWARE_VALIDATION" in data["hardware_note"]
    assert set(data["cases"]) == {"a"}
    json.dumps(data)


def test_artifact_same_arch_note():
    from hugrgate.edge.platform import pi_baseline
    bench = EdgeBenchmark("t", platform=_info(arch="aarch64"),
                          baseline_board=pi_baseline("Raspberry Pi 5"))
    bench.add("a", lambda: None, iterations=3)
    bench.run()
    assert "SURROGATE HOST" not in bench.artifact()["hardware_note"]


def test_load_artifact_rejects_garbage(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema": "nope"}')
    with pytest.raises(BenchmarkError, match="unsupported artifact schema"):
        load_artifact(bad)
    empty = tmp_path / "empty.json"
    empty.write_text('{"schema": "edge-bench/1", "cases": {}}')
    with pytest.raises(BenchmarkError, match="no cases"):
        load_artifact(empty)
    with pytest.raises(BenchmarkError, match="cannot load"):
        load_artifact(tmp_path / "missing.json")


# --- comparison --------------------------------------------------------------------------

def _art(cases: dict) -> dict:
    return {"schema": ARTIFACT_SCHEMA, "cases": cases}


def test_compare_detects_regression():
    cur = _art({"a": {"mean_s": 0.12}, "b": {"mean_s": 0.05}})
    base = _art({"a": {"mean_s": 0.10}, "b": {"mean_s": 0.05}})
    out = compare_artifacts(cur, base, threshold=0.10)
    assert out["cases"]["a"]["regressed"] is True
    assert out["cases"]["a"]["ratio"] == pytest.approx(1.2)
    assert out["cases"]["b"]["regressed"] is False
    assert out["regressed"] == ["a"]
    assert out["passed"] is False


def test_compare_tolerates_within_threshold():
    cur = _art({"a": {"mean_s": 0.105}})
    base = _art({"a": {"mean_s": 0.10}})
    out = compare_artifacts(cur, base, threshold=0.10)
    assert out["passed"] is True


def test_compare_reports_missing_cases():
    out = compare_artifacts(_art({"a": {"mean_s": 1.0}}),
                            _art({"b": {"mean_s": 1.0}}))
    assert out["cases"]["a"]["status"] == "missing-in-baseline"
    assert out["cases"]["b"]["status"] == "missing-in-current"


def test_compare_rejects_negative_threshold():
    with pytest.raises(BenchmarkError, match="threshold"):
        compare_artifacts(_art({}), _art({}), threshold=-1.0)


# --- representative suite ---------------------------------------------------------------------

def test_edge_bench_suite_runs():
    bench = edge_bench_suite(iterations=5)
    results = bench.run()
    assert set(results) == {"decide/rules", "quant/int8-matvec",
                            "quant/int4-roundtrip", "storage/put-flush",
                            "telemetry/record"}
    for r in results.values():
        assert r.mean_s >= 0 and r.iterations == 5


# --- slice 197: Pi benchmark suite -------------------------------------------------

from hugrgate.edge.bench import pi_bench_suite


def test_pi_bench_suite_binds_baseline():
    bench = pi_bench_suite("Raspberry Pi 5", iterations=5)
    assert bench.baseline_board is not None
    assert bench.baseline_board.board == "Raspberry Pi 5"
    assert "raspberry-pi-5" in bench.name
    results = bench.run()
    assert {"platform/audit", "memory/refresh"} <= set(results)
    assert len(results) == 7  # 5 standard + 2 Pi-specific


def test_pi_bench_suite_marks_surrogate_host():
    bench = pi_bench_suite("Raspberry Pi Zero 2 W", iterations=3)
    bench.run()
    note = bench.artifact()["hardware_note"]
    assert "Raspberry Pi Zero 2 W" in note
    # this host is x86_64 -> surrogate marking required
    import platform as _platform
    if _platform.machine().lower() not in ("aarch64", "arm64"):
        assert "SURROGATE HOST" in note


def test_pi_bench_suite_unknown_board_raises():
    with pytest.raises(ValueError, match="known models"):
        pi_bench_suite("Raspberry Pi 400")
