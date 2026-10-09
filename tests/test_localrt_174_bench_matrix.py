"""Slice 174 — local runtime benchmark matrix.

Unit tests for ``hugrgate.runtimes.bench_matrix``. These tests use
tiny configs and write artifacts to ``tmp_path`` ONLY — they must
never rewrite ``benchmarks/localrt-matrix.json``. The real artifact
is regenerated with ``python -m hugrgate.runtimes.bench_matrix``
after the final test run.
"""

from __future__ import annotations

import json

import pytest

from hugrgate.errors import SpecError
from hugrgate.runtimes import FakeRuntime, RuntimeRegistry
from hugrgate.runtimes.bench_matrix import (
    ARTIFACT_PATH,
    BenchConfig,
    BenchMatrix,
    BenchResult,
    bench_all,
    bench_runtime,
    build_default_registry,
    write_artifact,
)
from hugrgate.runtimes.ollama import OllamaRuntime


def _small_config(**kwargs) -> BenchConfig:
    return BenchConfig(rounds=3, warmup_rounds=1, **kwargs)


def _fake(name: str = "fake", **kwargs) -> FakeRuntime:
    rt = FakeRuntime(**kwargs)
    rt.name = name
    return rt


# -- config ------------------------------------------------------------------------------

def test_config_rejects_bad_rounds():
    with pytest.raises(SpecError):
        BenchConfig(rounds=0)
    with pytest.raises(SpecError):
        BenchConfig(warmup_rounds=-1)


# -- bench_runtime -------------------------------------------------------------------------

def test_bench_runtime_measures_all_capabilities():
    results = bench_runtime(_fake(), _small_config())
    by_op = {r.operation: r for r in results}
    assert set(by_op) == {"generate", "embed", "classify"}
    for result in results:
        assert result.ok is True
        assert result.n == 3
        assert result.error is None
        assert result.p50_s is not None and result.p50_s >= 0
        assert result.p95_s >= result.p50_s
        assert result.mean_s is not None


def test_bench_runtime_detects_injected_latency():
    results = bench_runtime(_fake(latency_s=0.05), _small_config())
    gen = next(r for r in results if r.operation == "generate")
    assert gen.p50_s is not None and gen.p50_s >= 0.04


def test_bench_runtime_records_unavailable_adapter():
    rt = OllamaRuntime(model="tiny")  # no server in CI
    results = bench_runtime(rt, _small_config())
    assert results, "unavailable adapters must still produce rows"
    assert all(r.ok is False for r in results)
    assert all("BackendUnavailable" in (r.error or "") for r in results)
    assert all(r.n == 0 for r in results)


def test_bench_result_stats_math():
    r = BenchResult(runtime="x", operation="generate", ok=True,
                    latencies_s=[0.1, 0.2, 0.3, 0.4])
    assert r.n == 4
    assert r.p50_s == pytest.approx(0.3)  # idx int(4*0.5)=2
    assert r.p95_s == pytest.approx(0.4)
    assert r.mean_s == pytest.approx(0.25)
    d = r.to_dict()
    assert d["min_s"] == pytest.approx(0.1)
    assert d["max_s"] == pytest.approx(0.4)


def test_bench_result_empty_stats_are_none():
    r = BenchResult(runtime="x", operation="generate", ok=False,
                    error="nope")
    assert r.p50_s is None and r.p95_s is None and r.mean_s is None


# -- bench_all / artifact --------------------------------------------------------------------

def test_bench_all_aggregates_registry():
    reg = RuntimeRegistry()
    reg.register(_fake("a"))
    reg.register(_fake("b"))
    matrix = bench_all(reg, _small_config())
    assert len(matrix.results) == 6  # 2 runtimes x 3 ops
    assert {r.runtime for r in matrix.results} == {"a", "b"}


def test_write_artifact_schema(tmp_path):
    reg = RuntimeRegistry()
    reg.register(_fake("a"))
    matrix = bench_all(reg, _small_config())
    matrix.note = "test note"
    path = write_artifact(tmp_path / "m.json", matrix)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == "hugrgate.localrt-matrix/1"
    assert data["note"] == "test note"
    assert data["config"]["rounds"] == 3
    assert data["environment"]["python"]
    assert len(data["results"]) == 3
    assert data["results"][0]["runtime"] == "a"


def test_write_artifact_creates_parent_dirs(tmp_path):
    matrix = BenchMatrix()
    path = write_artifact(tmp_path / "sub" / "dir" / "m.json", matrix)
    assert path.exists()


def test_default_registry_shape():
    registry, note = build_default_registry()
    names = registry.list()
    assert "fake" in names and "fake-delayed-50ms" in names
    assert len(names) == 10  # 2 fakes + 8 adapters
    assert "Synthetic baseline" in note


def test_tests_do_not_touch_real_artifact(tmp_path):
    # Guard: this module's tests must never write the real artifact.
    assert ARTIFACT_PATH.name == "localrt-matrix.json"
    assert str(ARTIFACT_PATH) == "benchmarks/localrt-matrix.json"
    assert tmp_path != ARTIFACT_PATH.parent
