"""Slice 016 — serialization contracts.

Every HugrGate value object that crosses a process boundary must
round-trip: ``from_dict(to_dict(x)) == x``, and ``to_dict(x)`` must be
JSON-serializable for ordinary values. This pins the contract and
covers the types that had no serialization at all.
"""

from __future__ import annotations

import json

import pytest

from hugrgate.client import (
    policy_from_dict, policy_to_dict, result_from_dict,
)
from hugrgate.errors import PolicyError, SpecError
from hugrgate.ladder import LadderRung
from hugrgate.policy import DecisionPolicy
from hugrgate.provenance import DecisionRecord, ProvenanceStore
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec
from hugrgate.threshold import NumericBand, ThresholdConfig


def _json_roundtrip(obj):
    """to_dict output must survive a JSON round-trip."""
    return json.loads(json.dumps(obj.to_dict()))


# --- DecisionSpec ------------------------------------------------------------

def test_spec_roundtrip():
    for spec in (
        DecisionSpec(type="categorical", options=["a", "b", "c"]),
        DecisionSpec(type="ordinal", levels=["low", "high"]),
        DecisionSpec(type="numeric", minimum=0.0, maximum=1.0),
        DecisionSpec(type="binary", statement="escalate?"),
        DecisionSpec(type="multilabel", labels=["x", "y"]),
    ):
        assert DecisionSpec.from_dict(_json_roundtrip(spec)) == spec


def test_spec_from_dict_rejects_unknown_keys():
    with pytest.raises(SpecError):
        DecisionSpec.from_dict({"type": "binary", "bogus": 1})


# --- DecisionResult ----------------------------------------------------------

def test_result_roundtrip():
    r = DecisionResult(value="a", probability=0.7,
                       distribution={"a": 0.7, "b": 0.3},
                       uncertainty=0.1, backend="rules", model="m",
                       latency_ms=2.5, calibration_profile="platt",
                       fallback_used=True, metadata={"k": "v"})
    assert result_from_dict(_json_roundtrip(r)) == r


def test_result_multilabel_roundtrip():
    r = DecisionResult(value=["a"], probability=0.8,
                       distribution={"a": 0.8, "b": 0.2})
    assert result_from_dict(r.to_dict()) == r


# --- DecisionPolicy ----------------------------------------------------------

def test_policy_roundtrip():
    p = DecisionPolicy(minimum_probability=0.6, maximum_latency_ms=100.0,
                       remote_inference=True, allowed_backends=["a"],
                       preferred_backends=["a"], fallback_behavior="safe_default",
                       privacy_class="strict", max_cost=1.5,
                       review_band=(0.5, 0.7))
    assert policy_from_dict(_json_roundtrip(p)) == p


def test_policy_from_dict_rejects_unknown_keys():
    with pytest.raises(PolicyError):
        policy_from_dict({"minimum_probability": 0.5, "bogus": 1})


# --- DecisionRecord ----------------------------------------------------------

def test_record_roundtrip_through_store():
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    r = DecisionResult(value="a", probability=0.8,
                       distribution={"a": 0.8, "b": 0.2})
    rec = DecisionRecord.from_decision({"x": 1}, spec, r,
                                       policy_threshold=0.5)
    store = ProvenanceStore()
    store.append(rec)
    stored = store.recent(1)[0]
    back = DecisionRecord.from_dict(_json_roundtrip(stored))
    assert back == stored
    # hashes survive the trip, so the chain still verifies
    assert back.record_hash == stored.record_hash
    assert back.prev_hash == stored.prev_hash


def test_record_from_dict_missing_keys():
    with pytest.raises(SpecError, match="missing key"):
        DecisionRecord.from_dict({"request_hash": "x"})


# --- ThresholdConfig / NumericBand --------------------------------------------

def test_threshold_config_roundtrip():
    cfg = ThresholdConfig(
        per_option={"escalate": 0.9},
        ordinal_minimum=("moderate", 0.75),
        numeric_bands=[NumericBand("normal", 36.0, 37.5),
                       NumericBand("fever", 37.5, 42.0,
                                   min_probability=0.9)],
        global_minimum=0.5,
    )
    back = ThresholdConfig.from_dict(_json_roundtrip(cfg))
    assert back == cfg


def test_threshold_config_from_dict_rejects_unknown_keys():
    with pytest.raises(PolicyError, match="unknown ThresholdConfig"):
        ThresholdConfig.from_dict({"per_option": {}, "bogus": 1})


def test_numeric_band_defaults():
    b = NumericBand.from_dict({"name": "n", "lo": 0.0, "hi": 1.0})
    assert b.min_probability == 0.0


# --- LadderRung ---------------------------------------------------------------

def test_ladder_rung_roundtrip():
    rung = LadderRung("fast", min_confidence=0.9, latency_budget_ms=50.0)
    assert LadderRung.from_dict(_json_roundtrip(rung)) == rung


def test_ladder_rung_from_dict_rejects_unknown_keys():
    with pytest.raises(SpecError, match="unknown LadderRung"):
        LadderRung.from_dict({"backend_name": "x", "bogus": 1})


def test_ladder_rung_from_dict_validates():
    with pytest.raises(SpecError):
        LadderRung.from_dict({"backend_name": "x", "min_confidence": 2.0})
