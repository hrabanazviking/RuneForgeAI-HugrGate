"""Slice 238 — Privacy-preserving provenance.

Tests per-class provenance modes, value fingerprints, the
privacy-aware store (including chain verification over redacted
records), core/ladder integration, and adversarial cases (no raw
values anywhere in any mode; forbidden leaks nothing).
"""

from __future__ import annotations

import pytest

from hugrgate.policy import DecisionPolicy
from hugrgate.privacy_provenance import (
    PrivacyAwareProvenanceStore,
    fingerprint_state,
    privacy_preserving_record,
)
from hugrgate.provenance import ProvenanceStore
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec


def make_spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def make_result():
    return DecisionResult(value="a", probability=0.9,
                          distribution={"a": 0.9, "b": 0.1},
                          backend="stub", model="m")


STATE = {"ssn": "123-45-6789", "name": "Volmarr", "age": 54}


def record_for(cls, **kw):
    return privacy_preserving_record(
        STATE, make_spec(), make_result(),
        DecisionPolicy(privacy_class=cls), **kw)


@pytest.mark.parametrize("cls", ["public", "standard", "sensitive"])
def test_key_modes_carry_keys_not_values(cls):
    record = record_for(cls)
    assert record.metadata["state_keys"] == ["ssn", "name", "age"]
    assert record.metadata["privacy_class"] == cls
    assert record.metadata["redacted"] is False
    blob = repr(record.metadata)
    assert "123-45-6789" not in blob


def test_strict_mode_redacted():
    record = record_for("strict")
    assert "state_keys" not in record.metadata
    assert record.metadata["redacted"] is True
    assert record.metadata["privacy_class"] == "strict"
    assert "123-45-6789" not in repr(record.metadata)


def test_forbidden_mode_nothing():
    record = record_for("forbidden")
    assert "state_keys" not in record.metadata
    assert "value_fingerprints" not in record.metadata
    assert record.metadata == {"privacy_class": "forbidden",
                               "redacted": True}


def test_fingerprints_opt_in():
    record = record_for("sensitive", fingerprints=True)
    fps = record.metadata["value_fingerprints"]
    assert set(fps) == {"ssn", "name", "age"}
    assert all(v.startswith("sha256:") for v in fps.values())
    assert "123-45-6789" not in repr(fps)
    # Deterministic: same input -> same fingerprints.
    assert record_for("sensitive", fingerprints=True).metadata[
        "value_fingerprints"] == fps


def test_fingerprints_not_attached_when_redacted():
    record = record_for("strict", fingerprints=True)
    assert "value_fingerprints" not in record.metadata


def test_fingerprint_state_validates():
    with pytest.raises(ValueError):
        fingerprint_state({"a": 1}, digest_chars=0)
    fps = fingerprint_state({"a": 1, "b": {"c": 2}})
    assert set(fps) == {"a", "b.c"}


def test_store_appends_and_chains():
    store = PrivacyAwareProvenanceStore()
    for cls in ["public", "strict", "forbidden", "sensitive"]:
        store.append_decision(STATE, make_spec(), make_result(),
                              DecisionPolicy(privacy_class=cls))
    assert store.count() == 4
    assert store.verify_chain() is True
    classes = [r.metadata["privacy_class"]
               for r in store.recent(4)]
    assert classes == ["public", "strict", "forbidden", "sensitive"]


def test_store_returns_copy():
    store = PrivacyAwareProvenanceStore()
    record = store.append_decision(STATE, make_spec(), make_result(),
                                   DecisionPolicy())
    record.metadata["tampered"] = True
    assert "tampered" not in store.recent(1)[0].metadata


def test_store_rejects_wrong_type():
    store = PrivacyAwareProvenanceStore()
    with pytest.raises(TypeError):
        store.append("not a record")


def test_core_integration(stub_backend):
    from hugrgate.backend import BackendRegistry
    from hugrgate.core import HugrGate

    reg = BackendRegistry()
    reg.register(stub_backend)
    gate = HugrGate(registry=reg)
    gate.decide({"secret": "s3cr3t"}, make_spec(),
                DecisionPolicy(privacy_class="strict"))
    record = gate.provenance.recent(1)[0]
    assert "state_keys" not in record.metadata
    assert record.metadata["privacy_class"] == "strict"
    assert "s3cr3t" not in repr(record.metadata)


def test_ladder_integration(stub_backend):
    from hugrgate.backend import BackendRegistry
    from hugrgate.ladder import LadderRouter, LadderRung
    reg = BackendRegistry()
    reg.register(stub_backend)
    store = ProvenanceStore()
    router = LadderRouter(
        rungs=[LadderRung("stub", 0.0)], registry=reg,
        provenance=store)
    router.decide({"secret": "s3cr3t"}, make_spec(),
                  DecisionPolicy(privacy_class="forbidden"))
    record = router.provenance.recent(1)[0]
    assert record.metadata["privacy_class"] == "forbidden"
    assert "state_keys" not in record.metadata


def test_adversarial_no_raw_values_in_any_mode():
    secret = "super-secret-value-12345"
    state = {"field": secret, "nested": {"deep": secret}}
    for cls in ["public", "standard", "sensitive", "strict", "forbidden"]:
        record = privacy_preserving_record(
            state, make_spec(), make_result(),
            DecisionPolicy(privacy_class=cls), fingerprints=True)
        assert secret not in repr(record.metadata), cls
        assert secret not in repr(record.to_dict()), cls


def test_adversarial_request_hash_still_binds_state():
    # Even in "none" mode the request_hash commits to the full state,
    # so the record is still bound to what was decided.
    r1 = record_for("forbidden")
    assert len(r1.request_hash) == 16
    r2 = privacy_preserving_record(
        {"other": 1}, make_spec(), make_result(),
        DecisionPolicy(privacy_class="forbidden"))
    assert r1.request_hash != r2.request_hash
