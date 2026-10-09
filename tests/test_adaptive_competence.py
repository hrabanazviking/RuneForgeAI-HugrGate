"""Slice 137 — backend competence profiles tests."""

from __future__ import annotations

import time

import pytest

from hugrgate.adaptive.competence import (
    BackendCompetenceProfiles,
    CompetenceProfile,
    wilson_lower_bound,
)
from hugrgate.adaptive.telemetry import RouteEvent, TelemetryStore
from hugrgate.errors import SpecError


def labeled_event(rid, chosen, quality):
    return RouteEvent(
        request_id=rid, timestamp=time.time(),
        spec={"type": "categorical"}, features={"f": 1.0},
        candidates=["a", "b"], propensities={"a": 0.5, "b": 0.5},
        chosen=chosen, policy_version="v1", privacy_class="standard",
        latency_ms=10.0, cost=0.1,
        outcome={"quality": quality, "source": "test"})


# --- success ---------------------------------------------------------------

def test_observe_accumulates_profile():
    reg = BackendCompetenceProfiles()
    reg.observe("a", quality=0.9, latency_ms=100.0, cost=0.5)
    reg.observe("a", quality=0.5, latency_ms=200.0, cost=1.5)
    p = reg.get("a")
    assert p.attempts == 2
    assert p.successes == 1  # threshold 0.7: only 0.9 counts
    assert p.mean_quality == pytest.approx(0.7)
    assert p.mean_latency_ms == pytest.approx(150.0)
    assert p.mean_cost == pytest.approx(1.0)

def test_wilson_prefers_proven_over_lucky():
    # 1/1 = 100% observed, but Wilson is skeptical of n=1.
    lucky = wilson_lower_bound(1, 1)
    proven = wilson_lower_bound(85, 100)
    assert proven > lucky
    assert wilson_lower_bound(0, 0) == 0.0
    assert 0.0 <= wilson_lower_bound(7, 10) <= 0.7

def test_ranked_orders_by_wilson_lower():
    reg = BackendCompetenceProfiles()
    reg.observe("lucky", quality=1.0)  # 1/1
    for _ in range(20):
        reg.observe("steady", quality=0.9)  # 20/20
    ranked = reg.ranked()
    assert ranked[0].backend == "steady"
    assert ranked[1].backend == "lucky"

def test_update_from_telemetry_skips_shadow_and_unlabeled():
    store = TelemetryStore()
    store.record(labeled_event("r1", "a", 0.9))
    shadowed = labeled_event("r2", "a", 0.9)
    store.record(RouteEvent(**{**shadowed.__dict__, "shadow": True}))
    unlabeled = RouteEvent(
        request_id="r3", timestamp=time.time(), spec={"type": "binary"},
        features={}, candidates=["a"], propensities={"a": 1.0},
        chosen="a", policy_version="v1", privacy_class="standard")
    store.record(unlabeled)
    reg = BackendCompetenceProfiles()
    assert reg.update_from_telemetry(store.events()) == 1
    assert reg.get("a").attempts == 1

def test_serialization_round_trip():
    reg = BackendCompetenceProfiles(success_threshold=0.8)
    reg.observe("a", quality=0.9)
    data = reg.to_dict()
    assert data["schema"] == "adaptive-competence/v1"
    reg2 = BackendCompetenceProfiles.from_dict(data)
    assert reg2.get("a").attempts == 1
    assert reg2.success_threshold == 0.8

def test_get_returns_defensive_copy():
    reg = BackendCompetenceProfiles()
    reg.observe("a", quality=0.9)
    reg.get("a").attempts = 999
    assert reg.get("a").attempts == 1

def test_unknown_backend_returns_none():
    assert BackendCompetenceProfiles().get("ghost") is None
    assert "ghost" not in BackendCompetenceProfiles()

# --- failure ---------------------------------------------------------------

def test_observe_validates_inputs():
    reg = BackendCompetenceProfiles()
    with pytest.raises(SpecError):
        reg.observe("", quality=0.5)
    with pytest.raises(SpecError):
        reg.observe("a", quality=1.5)
    with pytest.raises(SpecError):
        reg.observe("a", quality=0.5, latency_ms=-1.0)

def test_bad_threshold_rejected():
    with pytest.raises(SpecError):
        BackendCompetenceProfiles(success_threshold=0.0)
    with pytest.raises(SpecError):
        BackendCompetenceProfiles(success_threshold=1.5)

def test_wilson_validates_counts():
    with pytest.raises(SpecError):
        wilson_lower_bound(5, 3)
    with pytest.raises(SpecError):
        wilson_lower_bound(-1, 3)

def test_wrong_schema_rejected():
    with pytest.raises(SpecError):
        BackendCompetenceProfiles.from_dict({"schema": "nope"})

def test_profile_invariants():
    with pytest.raises(SpecError):
        CompetenceProfile(backend="a", attempts=1, successes=2)
