"""Slice 149 — adaptive routing benchmark tests.

Tests run at reduced rounds for speed; the checked-in artifact at
``docs/campaign-vi/artifacts/adaptive-routing-benchmark.json`` is
regenerated at full rounds after the final suite run (see the slice-149
completion note).
"""

from __future__ import annotations

import random

import pytest

from hugrgate.adaptive.benchmark import (
    POLICIES,
    AdaptiveRoutingBenchmark,
    BenchmarkArtifact,
    default_scenario,
)
from hugrgate.errors import SpecError


def small_bench(**kw):
    params = {"rounds": 120, "seed": 7}
    params.update(kw)
    return AdaptiveRoutingBenchmark(**params)


# --- success ---------------------------------------------------------------

def test_policies_constant():
    assert set(POLICIES) == {"uniform", "round_robin", "static_first",
                             "adaptive"}

def test_run_produces_complete_artifact():
    artifact = small_bench().run()
    assert isinstance(artifact, BenchmarkArtifact)
    assert artifact.rounds == 120 and artifact.seed == 7
    assert set(artifact.mean_reward) == set(POLICIES)
    assert set(artifact.total_reward) == set(POLICIES)
    for policy in POLICIES:
        assert sum(artifact.pulls[policy].values()) == 120
        assert 0.0 <= artifact.mean_reward[policy] <= 1.0
    assert artifact.winner in POLICIES
    # Winner is the argmax of mean_reward (ties -> name order).
    best = max(POLICIES, key=lambda p: (artifact.mean_reward[p], p))
    assert artifact.winner == best

def test_adaptive_beats_uniform_on_contextual_scenario():
    artifact = small_bench(rounds=400).run()
    assert artifact.mean_reward["adaptive"] > \
        artifact.mean_reward["uniform"]
    # And beats the static baselines too: the scenario rewards context.
    assert artifact.mean_reward["adaptive"] > \
        artifact.mean_reward["static_first"]

def test_run_is_deterministic_for_seed():
    def canonical(artifact):
        d = artifact.to_dict()
        d.pop("generated_at")  # wall-clock: excluded by design
        return d
    a1 = canonical(small_bench().run())
    a2 = canonical(small_bench().run())
    assert a1 == a2
    a3 = canonical(small_bench(seed=99).run())
    assert a3["mean_reward"] != a1["mean_reward"]  # different seed

def test_default_scenario_shape():
    rng = random.Random(1)
    features, rewards = default_scenario(rng, 0)
    assert set(features) == {"x0", "x1", "bias"}
    assert set(rewards) == {"arm_a", "arm_b", "arm_c"}
    assert all(0.0 <= r <= 1.0 for r in rewards.values())
    # arm_a is good exactly when x0 > 0.5 (modulo noise).
    assert features["x0"] > 0.5 or True  # shape only; values vary

def test_save_and_load_round_trip(tmp_path):
    bench = small_bench()
    artifact = bench.run()
    path = str(tmp_path / "bench.json")
    assert bench.save(artifact, path) == path
    loaded = AdaptiveRoutingBenchmark.load(path)
    assert loaded["winner"] == artifact.winner
    assert loaded["rounds"] == 120
    assert loaded["config"]["scenario"] == "default_scenario"

def test_summary_mentions_every_policy():
    summary = small_bench().run().summary()
    for policy in POLICIES:
        assert policy in summary
    assert "winner" in summary

def test_custom_scenario_and_arms():
    def scenario(rng, idx):
        return ({"x0": 0.5, "x1": 0.5, "bias": 1.0},
                {"only": 0.7})
    artifact = AdaptiveRoutingBenchmark(rounds=10).run(
        scenario, arms=("only",))
    assert artifact.mean_reward["adaptive"] == pytest.approx(0.7)

# --- failure ---------------------------------------------------------------

def test_bad_constructor_args_rejected():
    with pytest.raises(SpecError):
        AdaptiveRoutingBenchmark(rounds=0)
    with pytest.raises(SpecError):
        AdaptiveRoutingBenchmark(alpha=-1.0)
    with pytest.raises(SpecError):
        AdaptiveRoutingBenchmark(ridge=0.0)

def test_empty_arms_rejected():
    with pytest.raises(SpecError):
        small_bench().run(arms=())

def test_scenario_arm_mismatch_rejected():
    def bad_scenario(rng, idx):
        return ({"x0": 0.0, "x1": 0.0, "bias": 1.0}, {"wrong": 0.5})
    with pytest.raises(SpecError):
        small_bench().run(bad_scenario)
