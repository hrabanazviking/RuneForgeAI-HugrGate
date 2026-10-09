"""Slice 139 — per-contract competence tests."""

from __future__ import annotations

import time

import pytest

from hugrgate import DecisionSpec
from hugrgate.adaptive.contract_competence import (
    PerContractCompetence,
    contract_of_event,
    contract_of_spec,
)
from hugrgate.adaptive.telemetry import RouteEvent, TelemetryStore
from hugrgate.errors import SpecError


def event_with_contract(rid, chosen, quality, contract=None, version=None,
                        spec_type="categorical"):
    spec = {"type": spec_type}
    metadata = {}
    if contract:
        metadata["contract"] = contract
    if version:
        metadata["version"] = version
    if metadata:
        spec["metadata"] = metadata
    return RouteEvent(
        request_id=rid, timestamp=time.time(), spec=spec,
        features={"f": 1.0}, candidates=["a", "b"],
        propensities={"a": 0.5, "b": 0.5}, chosen=chosen,
        policy_version="v1", privacy_class="standard",
        outcome={"quality": quality, "source": "test"})


# --- success ---------------------------------------------------------------

def test_contract_resolution_prefers_metadata():
    spec = DecisionSpec(type="categorical", options=["x", "y"],
                        metadata={"contract": "fraud-score", "version": "3"})
    assert contract_of_spec(spec) == "fraud-score/v3"
    spec2 = DecisionSpec(type="categorical", options=["x", "y"],
                         metadata={"contract": "fraud-score"})
    assert contract_of_spec(spec2) == "fraud-score"
    spec3 = DecisionSpec(type="categorical", options=["x", "y"])
    assert contract_of_spec(spec3) == "categorical"  # graceful fallback

def test_event_contract_resolution():
    e = event_with_contract("r", "a", 0.9, contract="fraud-score",
                            version="3")
    assert contract_of_event(e) == "fraud-score/v3"
    e2 = event_with_contract("r", "a", 0.9)
    assert contract_of_event(e2) == "categorical"

def test_contracts_distinguish_versions():
    comp = PerContractCompetence()
    comp.observe("a", "fraud-score/v3", quality=0.95)
    comp.observe("a", "fraud-score/v4", quality=0.40)
    v3 = comp.get("a", "fraud-score/v3")
    v4 = comp.get("a", "fraud-score/v4")
    assert v3.mean_quality == pytest.approx(0.95)
    assert v4.mean_quality == pytest.approx(0.40)
    # A domain average would have erased this distinction.
    assert v3.mean_quality != v4.mean_quality

def test_fallback_to_global():
    comp = PerContractCompetence()
    comp.observe("a", "fraud-score/v3", quality=0.9)
    assert comp.get_with_fallback("a", "fraud-score/v3").attempts == 1
    assert comp.get_with_fallback("a", "other/v1").attempts == 1
    assert comp.get_with_fallback("ghost", "fraud-score/v3") is None

def test_update_from_telemetry():
    store = TelemetryStore()
    store.record(event_with_contract("r1", "a", 0.9, contract="c1",
                                     version="2"))
    store.record(event_with_contract("r2", "b", 0.5))
    comp = PerContractCompetence()
    assert comp.update_from_telemetry(store.events()) == 2
    assert comp.get("a", "c1/v2").attempts == 1
    assert comp.get("b", "categorical").attempts == 1
    assert comp.contracts() == ["c1/v2", "categorical"]

def test_ranked_in_contract():
    comp = PerContractCompetence()
    comp.observe("shaky", "c1", quality=1.0)
    for _ in range(10):
        comp.observe("solid", "c1", quality=0.9)
    assert comp.ranked_in_contract("c1")[0].backend == "solid#c1"

def test_serialization_round_trip():
    comp = PerContractCompetence()
    comp.observe("a", "c1/v2", quality=0.9)
    comp2 = PerContractCompetence.from_dict(comp.to_dict())
    assert comp2.to_dict()["schema"] == "adaptive-contract-competence/v1"
    assert comp2.get("a", "c1/v2").attempts == 1

# --- failure ---------------------------------------------------------------

def test_empty_inputs_rejected():
    comp = PerContractCompetence()
    with pytest.raises(SpecError):
        comp.observe("", "c1", quality=0.5)
    with pytest.raises(SpecError):
        comp.observe("a", "", quality=0.5)

def test_wrong_schema_rejected():
    with pytest.raises(SpecError):
        PerContractCompetence.from_dict({"schema": "nope"})
