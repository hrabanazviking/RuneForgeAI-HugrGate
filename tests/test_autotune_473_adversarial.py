"""Slice 473 — optimizer adversarial tests. Unit tests."""

from __future__ import annotations

import pytest

from hugrgate.autotune.adversarial import (
    crash_storm_attack,
    label_poisoning_attack,
    latency_spike_attack,
    malicious_tuner_attack,
    poison_labels,
    spike_samples,
)
from hugrgate.autotune.controller import (
    ConfigStore,
    OptimizationController,
    TunableParameter,
)
from hugrgate.autotune.tuners._base import seeded_rng
from hugrgate.autotune.tuners.latency import LatencyBudgetTuner
from hugrgate.autotune.tuners.thresholds import ThresholdTuner, threshold_metric


def _dataset(seed=11, n=240):
    rng = seeded_rng(seed)
    out = []
    for _ in range(n // 2):
        out.append((rng.uniform(0.0, 0.45), 0))
    for _ in range(n // 2):
        out.append((rng.uniform(0.55, 1.0), 1))
    rng.shuffle(out)
    return out


def test_poison_labels_flips_fraction():
    data = _dataset()
    poisoned = poison_labels(data, 0.25, seed=3)
    flips = sum(1 for (_, a), (_, b) in zip(data, poisoned, strict=True) if a != b)
    assert flips == 60  # exactly 25% of 240
    assert [s for s, _ in poisoned] == [s for s, _ in data]  # scores kept
    with pytest.raises(ValueError):
        poison_labels(data, 1.5, seed=1)


def test_spike_samples():
    samples = {"a": [10.0] * 100, "b": [20.0] * 100}
    spiked = spike_samples(samples, 0.1, 5.0, seed=4)
    assert sum(1 for x in spiked["a"] if x == 50.0) == 10
    assert sum(1 for x in spiked["b"] if x == 100.0) == 10
    with pytest.raises(ValueError):
        spike_samples(samples, 0.1, 0.5, seed=1)


def test_label_poisoning_contained():
    data = _dataset()
    scores = [s for s, _ in data]
    labels = [lab for _, lab in data]

    def _factory(ds):
        return ThresholdTuner(param="min_prob", objective_id="f1",
                              dataset=ds, seed=1)

    result = label_poisoning_attack(
        _factory, data,
        clean_metric=lambda t: threshold_metric("f1", scores, labels, t),
        param="min_prob", poison_fraction=0.2, seed=7)
    # 20% label noise on separable data: the tuner must stay silent or
    # stay close. Report what actually happened.
    print("\npoisoning:", result.measurements)
    assert result.measurements["contained"] is True


def test_label_poisoning_heavy_noise_detected():
    # 40% label noise BREAKS the tuner: it chases the poisoned optimum
    # (threshold 0.0, clean F1 0.667 vs 1.0). The harness's job is to
    # measure that honestly. Breaking point documented in the slice
    # doc; mitigation is dataset provenance (slice 470), not tuner
    # magic — a tuner cannot distinguish poisoned labels from truth.
    data = _dataset()
    scores = [s for s, _ in data]
    labels = [lab for _, lab in data]

    def _factory(ds):
        return ThresholdTuner(param="min_prob", objective_id="f1",
                              dataset=ds, seed=1)

    result = label_poisoning_attack(
        _factory, data,
        clean_metric=lambda t: threshold_metric("f1", scores, labels, t),
        param="min_prob", poison_fraction=0.4, seed=7)
    print("\nheavy poisoning:", result.measurements)
    assert result.measurements["contained"] is False
    assert result.measurements["metric_drift"] > 0.10
    # ...but the drift is *measured*, not silent: the evidence trail
    # shows exactly what the poisoned tuner chose and its cost.


def test_latency_spike_contained():
    rng = seeded_rng(41)
    samples = {
        "routing_ms": [rng.uniform(20, 60) for _ in range(300)],
        "backend_ms": [rng.uniform(200, 600) for _ in range(300)],
    }

    def _factory(spiked):
        return LatencyBudgetTuner(
            objective_id="o", stages=["routing_ms", "backend_ms"],
            samples=spiked, total_budget_ms=600.0, seed=2)

    result = latency_spike_attack(_factory, samples, 600.0, 1.0,
                                  spike_fraction=0.1, spike_factor=10.0,
                                  seed=9)
    print("\nspike:", result.measurements)
    assert result.measurements["contained"] is True


def _controller():
    store = ConfigStore()
    store.register(TunableParameter(name="t", dtype="float", default=0.5,
                                    lo=0.0, hi=1.0))
    c = OptimizationController(store=store)
    c.register_objective("o", lambda values: 0.0)
    return c


def test_malicious_unknown_param_contained():
    result = malicious_tuner_attack(_controller(), {"ghost": 1.0})
    assert result.measurements["contained"] is True
    assert result.measurements["store_untouched"] is True


def test_malicious_out_of_bounds_contained():
    result = malicious_tuner_attack(_controller(), {"t": 999.0})
    assert result.measurements["contained"] is True


def test_malicious_wrong_type_contained():
    result = malicious_tuner_attack(_controller(), {"t": "evil"})
    assert result.measurements["contained"] is True


def test_crash_storm_contained():
    result = crash_storm_attack(_controller(), n_crashers=5)
    assert result.measurements["contained"] is True
    assert result.measurements["skipped"] == 5


def test_attack_result_serializable():
    result = crash_storm_attack(_controller(), n_crashers=2)
    d = result.to_dict()
    assert d["name"] == "crash_storm" and "measurements" in d
