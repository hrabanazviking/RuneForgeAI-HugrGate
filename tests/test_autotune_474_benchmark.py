"""Slice 474 — autotuning benchmark. Unit tests."""

from __future__ import annotations

import pytest

from hugrgate.autotune.benchmark import (
    AutotuneBenchmark,
    BenchmarkScenario,
)
from hugrgate.autotune.controller import TunableParameter
from hugrgate.autotune.tuners._base import seeded_rng
from hugrgate.autotune.tuners.cache import CachePolicyTuner
from hugrgate.autotune.tuners.latency import (
    LatencyBudgetTuner,
    empirical_tail,
)
from hugrgate.autotune.tuners.thresholds import ThresholdTuner, threshold_metric
from hugrgate.errors import AutotuneError


def _tdataset(seed=11, n=200):
    rng = seeded_rng(seed)
    out = []
    for _ in range(n // 2):
        out.append((rng.uniform(0.0, 0.45), 0))
    for _ in range(n // 2):
        out.append((rng.uniform(0.55, 1.0), 1))
    rng.shuffle(out)
    return out


def _threshold_scenario():
    data = _tdataset()
    scores = [s for s, _ in data]
    labels = [lab for _, lab in data]
    return BenchmarkScenario(
        name="threshold-f1",
        tuner=ThresholdTuner(param="min_prob", objective_id="f1",
                             dataset=data, seed=1),
        params=[TunableParameter(name="min_prob", dtype="float",
                                 default=0.9, lo=0.0, hi=1.0)],
        replay=lambda cfg: threshold_metric("f1", scores, labels,
                                            cfg["min_prob"]),
        data_fingerprint="synth-separable-v1")


def _latency_scenario():
    rng = seeded_rng(41)
    samples = {
        "routing_ms": [rng.uniform(20, 60) for _ in range(300)],
        "backend_ms": [rng.uniform(200, 600) for _ in range(300)],
    }

    def _replay(cfg):
        joint_ok = 1.0
        for st in samples:
            joint_ok *= 1.0 - empirical_tail(samples[st], cfg[st])
        return -(1.0 - joint_ok)  # negated overflow, higher is better

    return BenchmarkScenario(
        name="latency-budget",
        tuner=LatencyBudgetTuner(
            objective_id="overflow",
            stages=["routing_ms", "backend_ms"], samples=samples,
            total_budget_ms=600.0, seed=2),
        params=[TunableParameter(name="routing_ms", dtype="float",
                                 default=300.0, lo=1.0, hi=2000.0),
                TunableParameter(name="backend_ms", dtype="float",
                                 default=300.0, lo=1.0, hi=2000.0)],
        replay=_replay,
        data_fingerprint="synth-latency-v1")


def _cache_scenario():
    rng = seeded_rng(13)
    hot = [f"hot{i}" for i in range(5)]
    trace = []
    t = 0.0
    for _ in range(400):
        t += rng.uniform(0.5, 3.0)
        key = rng.choice(hot) if rng.random() < 0.8 \
            else f"cold{rng.randrange(200)}"
        trace.append((key, t, 10.0))

    from hugrgate.autotune.tuners.cache import simulate_trace

    def _replay(cfg):
        res = simulate_trace(trace, cfg["ttl"], int(cfg["maxsize"]),
                             cfg["evict"])
        return -res["total_cost"]

    return BenchmarkScenario(
        name="cache-policy",
        tuner=CachePolicyTuner(objective_id="cost", ttl_param="ttl",
                               size_param="maxsize", eviction_param="evict",
                               trace=trace, seed=1),
        params=[TunableParameter(name="ttl", dtype="float", default=60.0,
                                 lo=10.0, hi=600.0),
                TunableParameter(name="maxsize", dtype="int", default=32,
                                 lo=16, hi=4096),
                TunableParameter(name="evict", dtype="str", default="lru",
                                 choices=("lru", "lfu"))],
        replay=_replay,
        data_fingerprint="synth-cache-v1")


def test_benchmark_measures_improvement():
    bench = AutotuneBenchmark([_threshold_scenario(), _latency_scenario(),
                               _cache_scenario()])
    report = bench.run(seed=4)
    print("\n" + report.summary())
    assert len(report.results) == 3
    by_name = {r.scenario: r for r in report.results}
    # every tuner must measurably beat its baseline on its own data
    assert by_name["threshold-f1"].improvement > 0.05
    assert by_name["latency-budget"].improvement > 0
    assert by_name["cache-policy"].improvement > 0
    for r in report.results:
        assert r.proposal_id != ""
        assert r.seconds >= 0


def test_benchmark_deterministic():
    def _measured(report):
        return [{k: v for k, v in r.items()
                 if k not in ("seconds", "proposal_id")}
                for r in report.to_dict()["results"]]

    bench = AutotuneBenchmark([_threshold_scenario()])
    r1 = bench.run(seed=4)
    r2 = bench.run(seed=4)
    assert _measured(r1) == _measured(r2)


def test_benchmark_report_serializable():
    report = AutotuneBenchmark([_threshold_scenario()]).run(seed=1)
    d = report.to_dict()
    assert d["seed"] == 1 and len(d["results"]) == 1
    assert "improvement" in d["results"][0]
    assert "autotune benchmark" in report.summary()


def test_benchmark_rejects_bad_scenarios():
    with pytest.raises(AutotuneError):
        AutotuneBenchmark([])
    with pytest.raises(AutotuneError):
        AutotuneBenchmark([_threshold_scenario(), _threshold_scenario()])
    with pytest.raises(AutotuneError):
        BenchmarkScenario(name="x", tuner=_threshold_scenario().tuner,
                          params=[], replay=lambda c: 0.0)


def test_benchmark_replay_crash_surfaces():
    scenario = _threshold_scenario()
    scenario.replay = lambda cfg: 1.0 / 0.0
    with pytest.raises(AutotuneError):
        AutotuneBenchmark([scenario]).run(seed=1)
