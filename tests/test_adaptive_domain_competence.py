"""Slice 138 — per-domain competence tests."""

from __future__ import annotations

import time

import pytest

from hugrgate import DecisionSpec
from hugrgate.adaptive.domain_competence import (
    UNKNOWN_DOMAIN,
    PerDomainCompetence,
    domain_of_event,
    domain_of_spec,
)
from hugrgate.adaptive.telemetry import RouteEvent, TelemetryStore
from hugrgate.errors import SpecError


def event_with_domain(rid, chosen, quality, domain=None, spec_type="numeric"):
    spec = {"type": spec_type}
    if domain:
        spec["metadata"] = {"domain": domain}
    return RouteEvent(
        request_id=rid, timestamp=time.time(), spec=spec,
        features={"f": 1.0}, candidates=["a", "b"],
        propensities={"a": 0.5, "b": 0.5}, chosen=chosen,
        policy_version="v1", privacy_class="standard",
        outcome={"quality": quality, "source": "test"})


# --- success ---------------------------------------------------------------

def test_domain_resolution_order():
    spec = DecisionSpec(type="numeric", minimum=0.0, maximum=1.0,
                        metadata={"domain": "fraud"})
    assert domain_of_spec(spec) == "fraud"
    spec2 = DecisionSpec(type="numeric", minimum=0.0, maximum=1.0)
    assert domain_of_spec(spec2) == "numeric"  # type fallback
    assert domain_of_event(event_with_domain("r", "a", 0.9,
                                             domain="fraud")) == "fraud"
    assert domain_of_event(event_with_domain("r", "a", 0.9)) == "numeric"
    assert domain_of_event(RouteEvent(
        request_id="r", timestamp=0.0, spec={},
        features={}, candidates=["a"], propensities={"a": 1.0},
        chosen="a", policy_version="v", privacy_class="s",
    )) == UNKNOWN_DOMAIN

def test_observe_tracks_per_domain():
    comp = PerDomainCompetence()
    comp.observe("a", "fraud", quality=0.95)
    comp.observe("a", "fraud", quality=0.90)
    comp.observe("a", "chat", quality=0.30)
    fraud = comp.get("a", "fraud")
    chat = comp.get("a", "chat")
    assert fraud.attempts == 2 and fraud.mean_quality == pytest.approx(0.925)
    assert chat.attempts == 1 and chat.mean_quality == pytest.approx(0.30)

def test_fallback_ladder():
    comp = PerDomainCompetence()
    comp.observe("a", "fraud", quality=0.9)
    # Exact hit.
    assert comp.get_with_fallback("a", "fraud").attempts == 1
    # Unknown domain -> global backend profile.
    fallback = comp.get_with_fallback("a", "never-seen")
    assert fallback is not None and fallback.attempts == 1
    # Unknown backend -> None.
    assert comp.get_with_fallback("ghost", "fraud") is None

def test_update_from_telemetry_uses_event_domains():
    store = TelemetryStore()
    store.record(event_with_domain("r1", "a", 0.9, domain="fraud"))
    store.record(event_with_domain("r2", "a", 0.4, domain="chat"))
    comp = PerDomainCompetence()
    assert comp.update_from_telemetry(store.events()) == 2
    assert comp.get("a", "fraud").mean_quality == pytest.approx(0.9)
    assert comp.get("a", "chat").mean_quality == pytest.approx(0.4)
    assert comp.domains() == ["chat", "fraud"]

def test_ranked_in_domain():
    comp = PerDomainCompetence()
    comp.observe("shaky", "fraud", quality=1.0)  # 1/1, Wilson-skeptical
    for _ in range(10):
        comp.observe("solid", "fraud", quality=0.9)
    ranked = comp.ranked_in_domain("fraud")
    assert ranked[0].backend == "solid@fraud"

def test_serialization_round_trip():
    comp = PerDomainCompetence()
    comp.observe("a", "fraud", quality=0.9)
    comp2 = PerDomainCompetence.from_dict(comp.to_dict())
    assert comp2.get("a", "fraud").attempts == 1
    assert comp2.get_with_fallback("a", "other").attempts == 1

# --- failure ---------------------------------------------------------------

def test_empty_backend_or_domain_rejected():
    comp = PerDomainCompetence()
    with pytest.raises(SpecError):
        comp.observe("", "fraud", quality=0.5)
    with pytest.raises(SpecError):
        comp.observe("a", "", quality=0.5)
    with pytest.raises(SpecError):
        comp.observe("a", "fraud", quality=2.0)

def test_wrong_schema_rejected():
    with pytest.raises(SpecError):
        PerDomainCompetence.from_dict({"schema": "nope"})
