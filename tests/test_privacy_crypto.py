"""Slice 241 — Encrypted cache option.

Tests the stdlib AEAD (round-trip, tamper detection, key validation,
HKDF), the encrypted decision cache (sealed entries, privacy-class
rules, retention TTL, key-change failure), and adversarial cases
(bit-flips, truncation, wrong key, associated-data mismatch).
"""

from __future__ import annotations

import pickle

import pytest

from hugrgate.cache import cache_key
from hugrgate.errors import HugrGateError, SealError
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy_crypto import (
    EncryptedDecisionCache,
    SealedBox,
    hkdf,
)
from hugrgate.privacy_retention import RetentionPolicy
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


# -- SealedBox ---------------------------------------------------------------

def test_seal_open_round_trip():
    blob = SealedBox.seal(KEY, b"hello world")
    assert SealedBox.open(KEY, blob) == b"hello world"


def test_seal_is_randomized():
    assert SealedBox.seal(KEY, b"x") != SealedBox.seal(KEY, b"x")


def test_seal_empty_plaintext():
    assert SealedBox.open(KEY, SealedBox.seal(KEY, b"")) == b""


def test_seal_long_plaintext():
    data = bytes(range(256)) * 40
    assert SealedBox.open(KEY, SealedBox.seal(KEY, data)) == data


def test_associated_data_binds():
    blob = SealedBox.seal(KEY, b"data", associated=b"ctx-1")
    assert SealedBox.open(KEY, blob, associated=b"ctx-1") == b"data"
    with pytest.raises(SealError):
        SealedBox.open(KEY, blob, associated=b"ctx-2")


def test_wrong_key_fails():
    blob = SealedBox.seal(KEY, b"data")
    with pytest.raises(SealError) as exc:
        SealedBox.open(OTHER_KEY, blob)
    assert exc.value.reason == "auth"


def test_bit_flip_detected():
    blob = bytearray(SealedBox.seal(KEY, b"data"))
    blob[20] ^= 0x01
    with pytest.raises(SealError):
        SealedBox.open(KEY, bytes(blob))


def test_tag_flip_detected():
    blob = bytearray(SealedBox.seal(KEY, b"data"))
    blob[-1] ^= 0x01
    with pytest.raises(SealError):
        SealedBox.open(KEY, bytes(blob))


def test_truncation_detected():
    blob = SealedBox.seal(KEY, b"data")
    with pytest.raises(SealError) as exc:
        SealedBox.open(KEY, blob[:10])
    assert exc.value.reason == "truncated"


def test_non_bytes_blob():
    with pytest.raises(SealError):
        SealedBox.open(KEY, "not-bytes")


def test_key_validation():
    with pytest.raises(ValueError):
        SealedBox.seal(b"short", b"x")
    with pytest.raises(ValueError):
        SealedBox.open(b"short", b"x" * 48)
    with pytest.raises(TypeError):
        SealedBox.seal(KEY, "not-bytes")


def test_hkdf_vectors():
    # RFC 5869 test case 1 (SHA-256), truncated checks.
    ikm = bytes.fromhex("0b" * 22)
    salt = bytes.fromhex("000102030405060708090a0b0c")
    info = bytes.fromhex("f0f1f2f3f4f5f6f7f8f9")
    okm = hkdf(ikm, salt=salt, info=info, length=42)
    assert okm.hex() == (
        "3cb25f25faacd57a90434f64d0362f2a"
        "2d2d0a90cf1a5a4c5db02d56ecc4c5bf"
        "34007208d5b887185865")
    assert len(hkdf(ikm, length=16)) == 16
    with pytest.raises(ValueError):
        hkdf(b"", length=16)


def test_seal_error_taxonomy():
    err = SealError("bad tag", reason="auth")
    assert err.code == "seal_error"
    assert err.recoverable is False
    assert err.reason == "auth"
    rebuilt = HugrGateError.from_dict(err.to_dict())
    assert type(rebuilt) is SealError


# -- EncryptedDecisionCache ----------------------------------------------------

@pytest.fixture
def cache():
    return EncryptedDecisionCache(KEY)


def test_put_get_round_trip(cache):
    spec, policy = make_spec(), DecisionPolicy()
    assert cache.put({"x": 1}, spec, policy, make_result()) is True
    got = cache.get({"x": 1}, spec, policy)
    assert got is not None
    assert got.value == "a" and got.probability == pytest.approx(0.9)
    assert got.backend == "stub" and got.model == "m"


def test_entries_are_opaque(cache):
    spec, policy = make_spec(), DecisionPolicy()
    cache.put({"x": 1}, spec, policy, make_result())
    # The underlying store holds sealed blobs, not results.
    raw = cache._entries[cache_key({"x": 1}, spec, policy)].result
    assert not isinstance(raw, DecisionResult)
    assert b"stub" not in raw.blob  # backend name not visible


def test_strict_never_cached(cache):
    spec = make_spec()
    policy = DecisionPolicy(privacy_class="strict")
    assert cache.put({"x": 1}, spec, policy, make_result()) is False
    assert cache.get({"x": 1}, spec, policy) is None


def test_wrong_key_cache_fails_closed():
    spec, policy = make_spec(), DecisionPolicy()
    cache = EncryptedDecisionCache(KEY)
    cache.put({"x": 1}, spec, policy, make_result())
    # Simulate a key rotation: swap the key out from under the cache.
    cache._key = OTHER_KEY
    with pytest.raises(SealError):
        cache.get({"x": 1}, spec, policy)


def test_tampered_entry_fails_closed(cache):
    spec, policy = make_spec(), DecisionPolicy()
    cache.put({"x": 1}, spec, policy, make_result())
    entry = cache._entries[cache_key({"x": 1}, spec, policy)]
    blob = bytearray(entry.result.blob)
    blob[25] ^= 0xFF
    entry.result.blob = bytes(blob)
    with pytest.raises(SealError):
        cache.get({"x": 1}, spec, policy)


def test_retention_ttl_cap():
    cache = EncryptedDecisionCache(KEY, ttl_seconds=3600.0)
    spec = make_spec()
    policy = DecisionPolicy(privacy_class="sensitive")
    retention = RetentionPolicy({"sensitive": 0.05})
    assert cache.put({"x": 1}, spec, policy, make_result(),
                     retention=retention) is True
    assert cache.get({"x": 1}, spec, policy) is not None
    import time
    time.sleep(0.08)
    assert cache.get({"x": 1}, spec, policy) is None


def test_invalidate_backend(cache):
    spec, policy = make_spec(), DecisionPolicy()
    cache.put({"x": 1}, spec, policy, make_result())
    assert cache.invalidate_backend("stub") == 1
    assert cache.get({"x": 1}, spec, policy) is None


def test_key_id_hint_not_secret():
    cache = EncryptedDecisionCache(KEY)
    hint = cache.key_id_hint()
    assert hint.startswith("key:")
    assert KEY.hex() not in hint


def test_bad_key_rejected():
    with pytest.raises(ValueError):
        EncryptedDecisionCache(b"short")


def test_deepcopy_refused():
    import copy
    cache = EncryptedDecisionCache(KEY)
    with pytest.raises(TypeError):
        copy.deepcopy(cache)


def test_adversarial_cross_namespace_replay():
    # A blob sealed for one namespace does not open under another.
    spec, policy = make_spec(), DecisionPolicy()
    a = EncryptedDecisionCache(KEY, namespace="a")
    a.put({"x": 1}, spec, policy, make_result())
    entry = a._entries[cache_key({"x": 1}, spec, policy)]
    b = EncryptedDecisionCache(KEY, namespace="b")
    with pytest.raises(SealError):
        SealedBox.open(b._key, entry.result.blob,
                       associated=b._associated({"x": 1}, spec, policy))


def test_pickle_round_trip_fidelity(cache):
    spec, policy = make_spec(), DecisionPolicy()
    result = make_result()
    result.metadata["nested"] = {"a": [1, 2, 3]}
    cache.put({"x": 1}, spec, policy, result)
    got = cache.get({"x": 1}, spec, policy)
    assert got.metadata["nested"] == {"a": [1, 2, 3]}
    assert pickle.loads(pickle.dumps(result)).to_dict() == \
        got.to_dict()
