"""Slice 240 — Secure deletion hooks."""

from __future__ import annotations

import pytest

from hugrgate.privacy_deletion import (
    CryptoShredder,
    DeletionReceipt,
    SecureBuffer,
    SecureDeleter,
    shred_bytes,
)
from hugrgate.privacy_retention import RetentionPolicy, purge_expired
from hugrgate.provenance import DecisionRecord, ProvenanceStore
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec


def make_record(**metadata):
    record = DecisionRecord(
        request_hash="abc", spec={}, backend="b", model="m",
        metadata=dict(metadata))
    record.record_hash = "hash123"
    return record


def test_shred_bytes_overwrites():
    buf = bytearray(b"supersecret")
    shred_bytes(buf)
    assert buf == b"\x00" * 11
    assert b"supersecret" not in bytes(buf)


def test_shred_bytes_rejects_immutable():
    with pytest.raises(TypeError):
        shred_bytes(b"bytes")
    with pytest.raises(TypeError):
        shred_bytes("str")
    with pytest.raises(ValueError):
        shred_bytes(bytearray(b"x"), passes=0)


def test_shred_bytes_custom_passes():
    buf = bytearray(b"1234")
    shred_bytes(buf, passes=1)
    assert buf == b"\x00" * 4


def test_secure_buffer_shreds_on_exit():
    with SecureBuffer(b"secret") as buf:
        assert bytes(buf) == b"secret"
        handle = buf
    assert handle == b"\x00" * 6


def test_secure_buffer_shreds_on_exception():
    buf_ref = None
    with pytest.raises(RuntimeError):
        with SecureBuffer(b"secret") as buf:
            buf_ref = buf
            raise RuntimeError("boom")
    assert buf_ref == b"\x00" * 6


def test_secure_buffer_idempotent():
    buf = SecureBuffer(b"x")
    buf.shred()
    assert buf.shredded
    buf.shred()  # no error


def test_deleter_fires_hooks_and_receipts():
    deleter = SecureDeleter()
    calls: list[str] = []
    deleter.register(lambda r: calls.append(r.record_hash), name="audit")
    record = make_record(note="x")
    receipt = deleter(record)
    assert calls == ["hash123"]
    assert isinstance(receipt, DeletionReceipt)
    assert receipt.record_hash == "hash123"
    assert receipt.hooks_fired == ["audit"]
    assert receipt.to_dict()["record_hash"] == "hash123"


def test_deleter_shreds_bytearray_metadata():
    deleter = SecureDeleter()
    secret = bytearray(b"session-secret")
    record = make_record(session=secret, nested={"k": bytearray(b"xy")})
    receipt = deleter(record)
    assert secret == b"\x00" * 14
    assert set(receipt.shredded_fields) == {
        "metadata.session", "metadata.nested.k"}


def test_deleter_unregister():
    deleter = SecureDeleter()
    deleter.register(lambda r: None, name="a")
    deleter.register(lambda r: None, name="b")
    assert deleter.hooks == ["a", "b"]
    assert deleter.unregister("a") is True
    assert deleter.unregister("a") is False
    assert deleter.hooks == ["b"]


def test_crypto_shredder():
    dropped: list[str] = []
    shredder = CryptoShredder(drop_key=dropped.append)
    shredder.shred_key("key-1")
    shredder.shred_key("key-2")
    assert dropped == ["key-1", "key-2"]
    assert shredder.shredded_keys == ["key-1", "key-2"]


def test_purge_expired_with_secure_deleter():
    import time
    store = ProvenanceStore()
    record = DecisionRecord.from_decision(
        {"x": 1}, DecisionSpec(type="categorical", options=["a", "b"]),
        DecisionResult(value="a", probability=1.0,
                       distribution={"a": 1.0}))
    record.timestamp = time.time() - 200
    record.metadata["privacy_class"] = "standard"
    record.metadata["secret"] = bytearray(b"shred-me")
    store.append(record)

    receipts: list[DeletionReceipt] = []
    deleter = SecureDeleter()
    orig_call = deleter.__call__

    def capturing(r):
        receipt = orig_call(r)
        receipts.append(receipt)
        return receipt

    policy = RetentionPolicy({"standard": 100.0})
    removed = purge_expired(store, policy, on_purge=capturing)
    assert removed == 1
    assert store.count() == 0
    assert len(receipts) == 1
    assert receipts[0].record_hash
    # The stored copy's bytearray was shredded before removal.
    assert receipts[0].shredded_fields == ["metadata.secret"]


def test_adversarial_hook_exception_propagates():
    # A failing hook must not silently swallow deletion: it
    # propagates, and the caller sees the purge did not complete.
    deleter = SecureDeleter()

    def bad_hook(r):
        raise RuntimeError("hook failed")

    deleter.register(bad_hook, name="bad")
    with pytest.raises(RuntimeError):
        deleter(make_record())
