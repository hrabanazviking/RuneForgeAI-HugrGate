"""Slice 399 — agent-system benchmark."""

from __future__ import annotations

import pytest

from hugrgate.agents.benchmark import (
    AgentBenchmark,
    AgentBenchmarkConfig,
    _percentile,
)
from hugrgate.agents.simulator import AgentSimulator


def _factory():
    def make():
        sim = AgentSimulator()
        sim.add_agent("worker", "honest")
        sim.add_agent("flake", "faulty")
        return sim
    return make


def _script():
    return [
        {"ticket": "t1", "from": "boss", "to": "worker"},
        {"ticket": "t1", "from": "boss", "to": "flake"},
    ]


def test_benchmark_aggregates():
    bench = AgentBenchmark()
    config = AgentBenchmarkConfig(
        scenarios={"mixed": _script(), "clean": [
            {"ticket": "t1", "from": "boss", "to": "worker"}]},
        repetitions=3, seed=11)
    rep = bench.run(_factory(), config)
    assert rep.repetitions == 3 and rep.seed == 11
    by_name = {s.name: s for s in rep.scenarios}
    mixed = by_name["mixed"]
    assert mixed.runs == 3
    assert mixed.success_rate_mean == pytest.approx(0.5)
    assert mixed.total_failures == 3  # one flake per run x 3
    assert mixed.total_loops == 0 and mixed.total_runaways == 0
    assert mixed.latency_p50_ms >= 0.0
    assert mixed.latency_p95_ms >= mixed.latency_p50_ms
    clean = by_name["clean"]
    assert clean.success_rate_mean == 1.0
    assert clean.total_failures == 0
    assert rep.notes == ()  # deterministic: no notes


def test_report_wire_safe():
    bench = AgentBenchmark()
    rep = bench.run(_factory(), AgentBenchmarkConfig(
        scenarios={"s": _script()}, repetitions=2, seed=1))
    d = rep.to_dict()
    import json
    json.dumps(d)
    assert d["scenarios"][0]["name"] == "s"
    assert d["repetitions"] == 2


def test_nondeterminism_noted():
    n = {"i": 0}  # shared across runs: odd/even runs differ

    def factory():
        sim = AgentSimulator()

        def flippy(ctx):
            n["i"] += 1
            return "complete" if n["i"] % 2 else "fail"

        sim.add_agent("flip", flippy)
        return sim

    bench = AgentBenchmark()
    rep = bench.run(factory, AgentBenchmarkConfig(
        scenarios={"flip": [{"ticket": "t", "from": "b", "to": "flip"}]},
        repetitions=4, seed=5))
    assert any("nondeterministic" in note for note in rep.notes)


def test_percentile_edges():
    assert _percentile([], 50) == 0.0
    assert _percentile([5.0], 95) == 5.0
    assert _percentile([1.0, 2.0, 3.0, 4.0], 50) == pytest.approx(2.5)
    assert _percentile([1.0, 2.0, 3.0, 4.0], 0) == 1.0
    assert _percentile([1.0, 2.0, 3.0, 4.0], 100) == 4.0


def test_config_validation():
    with pytest.raises(ValueError):
        AgentBenchmarkConfig(scenarios={})
    with pytest.raises(ValueError):
        AgentBenchmarkConfig(scenarios={"s": []}, repetitions=0)
