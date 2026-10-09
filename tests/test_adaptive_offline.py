"""Slice 131 — offline policy learning tests."""

from __future__ import annotations

import time

import pytest

from hugrgate.adaptive.bandit import ContextualBanditAdapter
from hugrgate.adaptive.offline import OfflinePolicyLearning
from hugrgate.adaptive.telemetry import RouteEvent, TelemetryStore
from hugrgate.errors import SpecError

NAMES = ["x0", "bias"]


def logged_event(rid, chosen, features, propensity, quality,
                 shadow=False):
    return RouteEvent(
        request_id=rid, timestamp=time.time(),
        spec={"type": "categorical"}, features=features,
        candidates=["good", "bad"],
        propensities={"good": propensity if chosen == "good"
                      else 1.0 - propensity,
                      "bad": propensity if chosen == "bad"
                      else 1.0 - propensity},
        chosen=chosen, policy_version="v1", privacy_class="standard",
        immediate_quality=0.0,
        outcome={"quality": quality, "source": "test"},
        shadow=shadow)


def trained_store(n=40):
    store = TelemetryStore()
    for i in range(n):
        # Logging policy: mostly "good" (propensity 0.8), sometimes "bad".
        chosen = "good" if i % 5 else "bad"
        propensity = 0.8 if chosen == "good" else 0.2
        x0 = 1.0 if i % 2 else 0.0
        # True rewards: "good" earns 0.9, "bad" earns 0.2 regardless.
        quality = 0.9 if chosen == "good" else 0.2
        store.record(logged_event(f"r{i}", chosen, {"x0": x0, "bias": 1.0},
                                  propensity, quality))
    return store


# --- success ---------------------------------------------------------------

def test_fit_learns_from_labeled_telemetry():
    learner = OfflinePolicyLearning(NAMES)
    adapter = learner.fit(trained_store().events())
    assert isinstance(adapter, ContextualBanditAdapter)
    d = adapter.select({"x0": 1.0, "bias": 1.0}, ["good", "bad"])
    assert d.arm == "good"
    diag = learner.diagnostics
    assert diag.n_used == 40 and diag.n_unlabeled == 0
    assert diag.effective_sample_size > 0

def test_fit_skips_shadow_and_unlabeled():
    store = trained_store(10)
    store.record(logged_event("shadow1", "good", {"x0": 1.0, "bias": 1.0},
                              0.8, 0.9, shadow=True))
    unlabeled = RouteEvent(
        request_id="u1", timestamp=time.time(), spec={"type": "binary"},
        features={"x0": 1.0, "bias": 1.0}, candidates=["good", "bad"],
        propensities={"good": 0.5, "bad": 0.5}, chosen="good",
        policy_version="v1", privacy_class="standard")
    store.record(unlabeled)
    learner = OfflinePolicyLearning(NAMES)
    learner.fit(store.events())
    diag = learner.diagnostics
    assert diag.n_shadow == 1
    assert diag.n_unlabeled == 1
    assert diag.n_used == 10

def test_ips_weighting_corrects_selection_bias():
    # Logging policy loves "bad" (propensity 0.9) but "bad" is worse.
    # IPS down-weights those frequent observations.
    store = TelemetryStore()
    for i in range(30):
        chosen = "bad" if i % 10 != 0 else "good"
        propensity = 0.9 if chosen == "bad" else 0.1
        quality = 0.2 if chosen == "bad" else 0.95
        store.record(logged_event(f"r{i}", chosen,
                                  {"x0": 1.0, "bias": 1.0},
                                  propensity, quality))
    learner = OfflinePolicyLearning(NAMES, max_weight=100.0)
    adapter = learner.fit(store.events())
    # 3 "good" obs at weight 10 vs 27 "bad" obs at weight ~1.11:
    # IPS-corrected, "good" still wins on merit.
    d = adapter.select({"x0": 1.0, "bias": 1.0}, ["good", "bad"])
    assert d.arm == "good"

def test_diagnostics_report_clipping():
    store = TelemetryStore()
    for i in range(5):
        store.record(logged_event(f"r{i}", "good", {"x0": 1.0, "bias": 1.0},
                                  0.01, 0.9))  # weight 100 -> clipped
    learner = OfflinePolicyLearning(NAMES, max_weight=10.0)
    learner.fit(store.events())
    assert learner.diagnostics.n_clipped == 5

def test_fit_store_convenience():
    learner = OfflinePolicyLearning(NAMES)
    adapter = learner.fit_store(trained_store(10))
    assert adapter.select({"x0": 0.0, "bias": 1.0},
                          ["good", "bad"]).arm == "good"

# --- failure ---------------------------------------------------------------

def test_fit_refuses_too_few_events():
    learner = OfflinePolicyLearning(NAMES, min_events=10)
    with pytest.raises(SpecError):
        learner.fit(trained_store(5).events())

def test_fit_with_no_usable_events_rejected():
    learner = OfflinePolicyLearning(NAMES)
    with pytest.raises(SpecError):
        learner.fit([])

def test_bad_propensity_events_skipped_and_counted():
    store = TelemetryStore()
    store.record(logged_event("r1", "good", {"x0": 1.0, "bias": 1.0},
                              1e-9, 0.9))  # below min_propensity
    store.record(logged_event("r2", "good", {"x0": 1.0, "bias": 1.0},
                              0.8, 0.9))
    learner = OfflinePolicyLearning(NAMES)
    learner.fit(store.events())
    assert learner.diagnostics.n_bad_propensity == 1
    assert learner.diagnostics.n_used == 1

def test_bad_constructor_args_rejected():
    with pytest.raises(SpecError):
        OfflinePolicyLearning(NAMES, min_propensity=0.0)
    with pytest.raises(SpecError):
        OfflinePolicyLearning(NAMES, max_weight=0.0)
    with pytest.raises(SpecError):
        OfflinePolicyLearning(NAMES, min_events=0)
