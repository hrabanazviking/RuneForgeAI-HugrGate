"""Slice 127 — outcome feedback API tests."""

from __future__ import annotations

import time

import pytest

from hugrgate import DecisionPolicy, DecisionResult, DecisionSpec
from hugrgate.adaptive.feedback import (
    OUTCOME_LABELS,
    OutcomeFeedbackAPI,
    OutcomeRecord,
)
from hugrgate.adaptive.telemetry import RouteEvent, TelemetryStore
from hugrgate.errors import SpecError


def make_store_with_event(rid="r1"):
    store = TelemetryStore()
    api = OutcomeFeedbackAPI(store)
    event = RouteEvent(
        request_id=rid, timestamp=time.time(),
        spec={"type": "binary"}, features={"f": 1.0},
        candidates=["a", "b"], propensities={"a": 0.5, "b": 0.5},
        chosen="a", policy_version="v1", privacy_class="standard")
    store.record(event)
    return store, api


# --- success ---------------------------------------------------------------

def test_record_outcome_attaches_label():
    store, api = make_store_with_event()
    rec = api.record_outcome("r1", quality=0.9, label="success",
                             source="human")
    assert isinstance(rec, OutcomeRecord)
    assert rec.quality == 0.9 and rec.label == "success"
    assert rec.received_at > 0
    event = store.get("r1")
    assert event.labeled and event.quality == 0.9
    assert event.outcome["source"] == "human"

def test_outcome_labels_are_the_documented_set():
    assert set(OUTCOME_LABELS) == {"success", "failure", "partial"}
    store, api = make_store_with_event()
    api.record_outcome("r1", quality=0.2, label="failure")
    assert store.get("r1").outcome["label"] == "failure"

def test_label_optional():
    store, api = make_store_with_event()
    rec = api.record_outcome("r1", quality=0.5)
    assert rec.label is None

def test_allow_overwrite_replaces_outcome():
    store, api = make_store_with_event()
    api.record_outcome("r1", quality=0.1, label="failure")
    api.record_outcome("r1", quality=0.9, label="success",
                       allow_overwrite=True)
    assert store.get("r1").quality == 0.9

def test_record_immediate_logs_decision_and_outcome():
    store = TelemetryStore()
    api = OutcomeFeedbackAPI(store)
    spec = DecisionSpec(type="categorical", options=["x", "y"])
    result = DecisionResult(value="x", probability=0.85,
                            distribution={"x": 0.85, "y": 0.15},
                            backend="rules", latency_ms=5.0)
    rid = api.record_immediate(
        spec=spec, features={"f": 1.0}, candidates=["rules", "llm"],
        propensities={"rules": 0.9, "llm": 0.1},
        chosen="rules", policy_version="v9", result=result,
        policy=DecisionPolicy(minimum_probability=0.5))
    event = store.get(rid)
    assert event.labeled and event.quality == 0.85
    assert event.outcome["source"] == "immediate"
    assert event.outcome["label"] == "success"
    assert event.metadata["policy_verdict"] == "accept"

def test_record_immediate_abstain_records_zero_quality():
    store = TelemetryStore()
    api = OutcomeFeedbackAPI(store)
    spec = DecisionSpec(type="categorical", options=["x", "y"])
    result = DecisionResult(value="x", probability=0.2,
                            distribution={"x": 0.2, "y": 0.8},
                            backend="rules")
    rid = api.record_immediate(
        spec=spec, features={}, candidates=["rules"],
        propensities={"rules": 1.0}, chosen="rules",
        policy_version="v9", result=result,
        policy=DecisionPolicy(minimum_probability=0.5))
    event = store.get(rid)
    assert event.quality == 0.0
    assert event.outcome["label"] == "failure"
    assert event.metadata["policy_verdict"] == "abstain"

# --- failure ---------------------------------------------------------------

def test_unknown_request_id_raises_keyerror():
    _, api = make_store_with_event()
    with pytest.raises(KeyError):
        api.record_outcome("ghost", quality=0.5)

def test_double_record_without_overwrite_rejected():
    _, api = make_store_with_event()
    api.record_outcome("r1", quality=0.5)
    with pytest.raises(SpecError):
        api.record_outcome("r1", quality=0.6)

def test_quality_out_of_bounds_rejected():
    _, api = make_store_with_event()
    with pytest.raises(SpecError):
        api.record_outcome("r1", quality=1.01)
    with pytest.raises(SpecError):
        api.record_outcome("r1", quality=-0.5)

def test_unknown_label_rejected():
    _, api = make_store_with_event()
    with pytest.raises(SpecError):
        api.record_outcome("r1", quality=0.5, label="meh")

def test_empty_source_rejected():
    _, api = make_store_with_event()
    with pytest.raises(SpecError):
        api.record_outcome("r1", quality=0.5, source="")

def test_outcome_record_validates_directly():
    with pytest.raises(SpecError):
        OutcomeRecord(request_id="r", quality=2.0)
    with pytest.raises(SpecError):
        OutcomeRecord(request_id="r", quality=0.5, label="bogus")
