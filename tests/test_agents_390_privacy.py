"""Slice 390 — agent privacy routing."""

from __future__ import annotations

import pytest

from hugrgate.agents.contract import AgentContract
from hugrgate.agents.privacy import PrivacyRouter, signal_privacy_class
from hugrgate.agents.types import AgentSignal
from hugrgate.errors import AgentNotFound


def _router():
    contracts = {
        "cleared": AgentContract(agent_id="cleared",
                                 privacy_clearance="sensitive"),
        "low": AgentContract(agent_id="low", privacy_clearance="public"),
    }
    return PrivacyRouter(contracts=contracts)


def _signal(cls):
    return AgentSignal(topic="t", payload={"privacy_class": cls})


def test_signal_privacy_class_default_and_invalid():
    assert signal_privacy_class(AgentSignal(topic="t")) == "public"
    assert signal_privacy_class(_signal("strict")) == "strict"
    with pytest.raises(ValueError):
        signal_privacy_class(
            AgentSignal(topic="t", payload={"privacy_class": "ultra"}))


def test_contract_clearance_fallback():
    r = _router()
    assert r.clearance_of("cleared") == "sensitive"
    assert r.clearance_of("low") == "public"
    assert r.clearance_of("ghost") is None
    assert r.check("cleared", "sensitive")
    assert r.check("cleared", "standard")
    assert not r.check("cleared", "strict")
    assert not r.check("ghost", "public")  # fail closed


def test_explicit_clearance_overrides_contract():
    r = _router()
    r.set_clearance("low", "strict")
    assert r.clearance_of("low") == "strict"
    assert r.check("low", "strict")
    with pytest.raises(ValueError):
        r.set_clearance("low", "ultra")


def test_route_filters_and_sorts():
    r = _router()
    out = r.route(_signal("sensitive"), ["low", "cleared", "ghost"])
    assert out == ("cleared",)
    out = r.route(_signal("public"), ["low", "cleared"])
    assert out == ("cleared", "low")  # sorted
    with pytest.raises(AgentNotFound) as ei:
        r.route(_signal("strict"), ["low", "cleared"])
    assert ei.value.details["privacy_class"] == "strict"
    with pytest.raises(ValueError):
        r.route(_signal("public"), [])


def test_stats():
    r = _router()
    r.route(_signal("public"), ["low"])
    try:
        r.route(_signal("strict"), ["low"])
    except AgentNotFound:
        pass
    s = r.stats()
    assert s["routed"] == 2 and s["denied_signals"] == 1
