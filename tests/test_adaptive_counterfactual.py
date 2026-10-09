"""Slice 144 — counterfactual route evaluation tests."""

from __future__ import annotations

import time

import pytest

from hugrgate.adaptive.bandit import ContextualBanditAdapter
from hugrgate.adaptive.counterfactual import (
    ESTIMATORS,
    CounterfactualEvaluator,
    PolicyValueEstimate,
)
from hugrgate.adaptive.telemetry import RouteEvent, TelemetryStore
from hugrgate.errors import SpecError

NAMES = ["x0", "bias"]


def logged(rid, chosen, propensity, quality, x0=1.0):
    other = "b" if chosen == "a" else "a"
    return RouteEvent(
        request_id=rid, timestamp=time.time(),
        spec={"type": "categorical"}, features={"x0": x0, "bias": 1.0},
        candidates=["a", "b"],
        propensities={chosen: propensity, other: 1.0 - propensity},
        chosen=chosen, policy_version="v1", privacy_class="standard",
        outcome={"quality": quality, "source": "test"})


def build_store(n=60):
    # Logging policy: uniform random (propensity 0.5 each).
    # True rewards: a=0.8, b=0.3 always.
    store = TelemetryStore()
    for i in range(n):
        chosen = "a" if i % 2 == 0 else "b"
        quality = 0.8 if chosen == "a" else 0.3
        store.record(logged(f"r{i}", chosen, 0.5, quality))
    return store


def always_a(features, candidates):
    return "a"


def always_b(features, candidates):
    return "b"


# --- success ---------------------------------------------------------------

def test_estimators_constant():
    assert set(ESTIMATORS) == {"ips", "snips", "dr"}

def test_snips_recovers_true_policy_value():
    ce = CounterfactualEvaluator(NAMES)
    est = ce.estimate(build_store().events(), always_a, estimator="snips")
    assert isinstance(est, PolicyValueEstimate)
    # Target always picks "a" (true reward 0.8); logging was uniform.
    assert est.value == pytest.approx(0.8, abs=0.05)
    assert est.n_used == 60 and est.n_skipped == 0
    assert est.effective_sample_size > 0

def test_ips_agrees_on_uniform_logging():
    ce = CounterfactualEvaluator(NAMES)
    ips = ce.estimate(build_store().events(), always_a, estimator="ips")
    assert ips.value == pytest.approx(0.8, abs=0.05)

def test_dr_uses_reward_model():
    ce = CounterfactualEvaluator(NAMES)
    dr = ce.estimate(build_store().events(), always_b, estimator="dr")
    # Target always picks "b" (true reward 0.3).
    assert dr.value == pytest.approx(0.3, abs=0.1)

def test_estimate_distinguishes_good_from_bad_policy():
    ce = CounterfactualEvaluator(NAMES)
    events = list(build_store().events())
    good = ce.estimate(events, always_a).value
    bad = ce.estimate(events, always_b).value
    assert good > bad

def test_contextual_target_policy():
    ce = CounterfactualEvaluator(NAMES)
    store = TelemetryStore()
    for i in range(40):
        x0 = 1.0 if i % 2 == 0 else 0.0
        chosen = "a" if (i // 2) % 2 == 0 else "b"
        # Reward depends on (arm, x0): a good iff x0=1, b good iff x0=0.
        quality = 0.9 if (chosen == "a") == (x0 == 1.0) else 0.1
        store.record(logged(f"r{i}", chosen, 0.5, quality, x0=x0))

    def smart(features, candidates):
        return "a" if features["x0"] == 1.0 else "b"

    est = ce.estimate(store.events(), smart)
    assert est.value == pytest.approx(0.9, abs=0.05)

def test_to_dict_fields():
    ce = CounterfactualEvaluator(NAMES)
    est = ce.estimate(build_store(10).events(), always_a)
    d = est.to_dict()
    assert d["estimator"] == "snips" and d["n_events"] == 10

# --- failure ---------------------------------------------------------------

def test_unknown_estimator_rejected():
    ce = CounterfactualEvaluator(NAMES)
    with pytest.raises(SpecError):
        ce.estimate(build_store(5).events(), always_a, estimator="magic")

def test_no_usable_events_rejected():
    ce = CounterfactualEvaluator(NAMES)
    with pytest.raises(SpecError):
        ce.estimate([], always_a)

def test_target_choosing_unknown_arm_rejected():
    ce = CounterfactualEvaluator(NAMES)
    def rogue(features, candidates):
        return "ghost"
    with pytest.raises(SpecError):
        ce.estimate(build_store(5).events(), rogue)

def test_bad_constructor_args_rejected():
    with pytest.raises(SpecError):
        CounterfactualEvaluator(NAMES, min_propensity=0.0)
    with pytest.raises(SpecError):
        CounterfactualEvaluator(NAMES, max_weight=-1.0)
