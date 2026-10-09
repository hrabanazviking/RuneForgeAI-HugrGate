"""Slice 124 — Ensemble benchmarks.

The harness is tested against tmp_path only: benchmark tests must
NEVER rewrite the committed JSON artifact (Campaign III lesson).
The real artifact is regenerated after the final test run, before
committing.
"""

from __future__ import annotations

import json

import pytest
from ensemble_fakes import CAT_SPEC, ConstantBackend

from hugrgate.ensemble import (
    STRATEGIES_BENCHMARKED,
    benchmark_scaling,
    benchmark_strategies,
    write_benchmark_report,
)
from hugrgate.errors import PolicyError

ALPHA = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}
BETA = {"alpha": 0.2, "beta": 0.6, "gamma": 0.2}


def _factory():
    # 2 of 3 vote alpha: every voting strategy should find it
    return [ConstantBackend("a", "alpha", ALPHA),
            ConstantBackend("b", "alpha", ALPHA),
            ConstantBackend("c", "beta", BETA)]


def _labeled(n=12):
    states = [{"x": i} for i in range(n)]
    labels = ["alpha"] * n
    return states, labels


# --- success -----------------------------------------------------------------

def test_benchmark_strategies_measures_all():
    states, labels = _labeled()
    report = benchmark_strategies(_factory, states, CAT_SPEC(),
                                  labels)
    assert set(report) == set(STRATEGIES_BENCHMARKED)
    for strategy, m in report.items():
        assert m["n"] == 12
        assert m["accuracy"] == pytest.approx(1.0), strategy
        assert 0.0 <= m["ece"] <= 1.0
        assert m["brier_score"] is not None
        assert m["wall_ms"] >= 0.0
        assert m["mean_latency_ms"] >= 0.0


def test_benchmark_detects_accuracy_differences():
    # labels disagree with the majority on half the states
    states = [{"x": i} for i in range(10)]
    labels = ["alpha"] * 5 + ["beta"] * 5
    report = benchmark_strategies(_factory, states, CAT_SPEC(),
                                  labels, strategies=["hard"])
    assert report["hard"]["accuracy"] == pytest.approx(0.5)


def test_benchmark_scaling():
    def factory(n):
        return [ConstantBackend(f"m{i}", "alpha", ALPHA)
                for i in range(n)]
    states, _ = _labeled(8)
    table = benchmark_scaling(factory, states, CAT_SPEC(),
                              sizes=[1, 2, 4])
    assert set(table) == {"1", "2", "4"}
    for key, row in table.items():
        assert row["members"] == int(key)
        assert row["states"] == 8
        assert row["ms_per_state"] >= 0.0


def test_write_benchmark_report_uses_tmp_path(tmp_path):
    states, labels = _labeled(4)
    report = {"strategies": benchmark_strategies(
        _factory, states, CAT_SPEC(), labels, strategies=["hard"])}
    path = write_benchmark_report(report, tmp_path / "bench.json")
    assert path.exists()
    loaded = json.loads(path.read_text())
    assert loaded["strategies"]["hard"]["accuracy"] == pytest.approx(
        1.0)


def test_report_is_json_serializable(tmp_path):
    states, labels = _labeled(4)
    report = benchmark_strategies(_factory, states, CAT_SPEC(),
                                  labels, strategies=["soft"])
    text = json.dumps(report, sort_keys=True)
    assert json.loads(text)["soft"]["n"] == 4


# --- failure -----------------------------------------------------------------

def test_benchmark_validation():
    states, labels = _labeled(4)
    with pytest.raises(PolicyError, match="states but"):
        benchmark_strategies(_factory, states, CAT_SPEC(),
                             labels[:-1])
    with pytest.raises(PolicyError, match="needs states"):
        benchmark_strategies(_factory, [], CAT_SPEC(), [])
    with pytest.raises(PolicyError, match="needs strategies"):
        benchmark_strategies(_factory, states, CAT_SPEC(), labels,
                             strategies=[])
    with pytest.raises(PolicyError, match="no members"):
        benchmark_strategies(lambda: [], states, CAT_SPEC(),
                             labels)
    with pytest.raises(PolicyError, match="needs sizes"):
        benchmark_scaling(lambda n: _factory()[:n], states,
                          CAT_SPEC(), sizes=[])
    with pytest.raises(PolicyError, match="produced"):
        benchmark_scaling(lambda n: [], states, CAT_SPEC(),
                          sizes=[2])


# --- boundary -----------------------------------------------------------------

def test_single_state_benchmark():
    states, labels = _labeled(1)
    report = benchmark_strategies(_factory, states, CAT_SPEC(),
                                  labels, strategies=["hard"])
    assert report["hard"]["accuracy"] == pytest.approx(1.0)
    assert report["hard"]["n"] == 1
