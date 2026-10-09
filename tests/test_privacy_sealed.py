"""Slice 242 — Encrypted provenance option."""

from __future__ import annotations

import pytest

from hugrgate.errors import SealError
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy_crypto import SealedBox
from hugrgate.privacy_provenance import SealedProvenanceStore
from hugrgate.provenance import DecisionRecord
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

KEY = bytes(range(32))
OTHER_KEY = bytes(reversed(range(32)))


def make_spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def make_result():
    return DecisionResult(value="a", probability=0.9,
                          distribution={"a": 0.9, "b": 0.1},
                          backend="stub", model="m")


@pytest.fixture
def store():
    return SealedProvenanceStore(KEY)


def test_append_and_recent_unseals(store):
    store.append_decision({"secret": "s3cr3t"}, make_spec(), make_result(),
                          DecisionPolicy(privacy_class="strict"))
    records = store.recent(1)
    assert len(records) == 1
    assert records[0].metadata["privacy_class"] == "strict"
    assert records[0].metadata["redacted"] is True
    assert store.count() == 1


def test_bodies_are_opaque(store):
    store.append_decision({"secret": "s3cr3t"}, make_spec(), make_result(),
                          DecisionPolicy())
    wrapper = store._records[0]
    assert wrapper.metadata.get("sealed") is True
    blob = wrapper.metadata["sealed_blob"]
    assert isinstance(blob, bytes)
    assert b"s3cr3t" not in blob  # sealed: body is opaque


def test_chain_verifies(store):
    for cls in ["public", "strict", "forbidden"]:
        store.append_decision({"x": cls}, make_spec(), make_result(),
                              DecisionPolicy(privacy_class=cls))
    assert store.verify_chain() is True


def test_by_hash(store):
    store.append_decision({"x": 1}, make_spec(), make_result(),
                          DecisionPolicy())
    record = store.recent(1)[0]
    found = store.by_hash(record.request_hash)
    assert found is not None
    assert found.record_hash == record.record_hash
    assert store.by_hash("nonexistent") is None


def test_wrong_key_fails_closed():
    store = SealedProvenanceStore(KEY)
    store.append_decision({"x": 1}, make_spec(), make_result(),
                          DecisionPolicy())
    store._key = OTHER_KEY
    with pytest.raises(SealError):
        store.recent(1)
    assert store.verify_chain() is False


def test_tampered_blob_detected(store):
    store.append_decision({"x": 1}, make_spec(), make_result(),
                          DecisionPolicy())
    wrapper = store._records[0]
    blob = bytearray(wrapper.metadata["sealed_blob"])
    blob[30] ^= 0xFF
    wrapper.metadata["sealed_blob"] = bytes(blob)
    with pytest.raises(SealError):
        store.recent(1)
    assert store.verify_chain() is False


def test_purge_rechains_and_reseals(store):
    for i in range(3):
        store.append_decision({"x": i}, make_spec(), make_result(),
                              DecisionPolicy())
    # Age the middle record by tampering its timestamp post-hoc via
    # unsealed view is impossible; purge by predicate instead.
    removed = store.purge(lambda r: r.probability < 0)  # none match
    assert removed == 0
    removed = store.purge(lambda r: True)  # all match
    assert removed == 3
    assert store.count() == 0
    assert store.verify_chain() is True


def test_purge_keeps_chain_sound(store):
    store.append_decision({"x": 1}, make_spec(), make_result(),
                          DecisionPolicy())
    store.append_decision({"x": 2}, make_spec(), make_result(),
                          DecisionPolicy())
    first_hash = store.recent(2)[0].request_hash
    removed = store.purge(lambda r: r.request_hash == first_hash)
    assert removed == 1
    assert store.count() == 1
    assert store.verify_chain() is True
    assert store.recent(1)[0].metadata  # unseals fine


def test_max_records_eviction():
    store = SealedProvenanceStore(KEY, max_records=2)
    for i in range(3):
        store.append_decision({"x": i}, make_spec(), make_result(),
                              DecisionPolicy())
    assert store.count() == 2
    assert store.evicted_count() == 1
    assert store.verify_chain() is True


def test_rejects_wrong_type(store):
    with pytest.raises(TypeError):
        store.append("nope")


def test_key_id_hint(store):
    assert store.key_id_hint().startswith("key:")
    assert KEY.hex() not in store.key_id_hint()


def test_bad_key_rejected():
    with pytest.raises(ValueError):
        SealedProvenanceStore(b"short")


def test_namespace_binds():
    a = SealedProvenanceStore(KEY, namespace="a")
    a.append_decision({"x": 1}, make_spec(), make_result(),
                      DecisionPolicy())
    blob = a._records[0].metadata["sealed_blob"]
    with pytest.raises(SealError):
        SealedBox.open(KEY, blob, associated=b"b:" + a._records[0].record_hash.encode())


def test_append_decision_returns_plaintext_copy(store):
    record = store.append_decision({"x": 1}, make_spec(), make_result(),
                                   DecisionPolicy())
    assert isinstance(record, DecisionRecord)
    assert "sealed_blob" not in record.metadata


def test_adversarial_plaintext_index_lies():
    # Attacker flips a wrapper's plaintext request_hash: the inner
    # record disagrees -> verify_chain fails.
    store = SealedProvenanceStore(KEY)
    store.append_decision({"x": 1}, make_spec(), make_result(),
                          DecisionPolicy())
    store._records[0].request_hash = "forged"
    assert store.verify_chain() is False
