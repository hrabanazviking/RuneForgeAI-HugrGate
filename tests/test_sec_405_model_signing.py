"""Slice 405 — signed model metadata.

HMAC-signed envelopes over canonical JSON: tampering with model
identity/version/capability claims is detected before the metadata
is trusted.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import HugrGateError, SignatureVerificationFailed
from hugrgate.security.model_signing import (
    ALGORITHM,
    ModelSigner,
    SignedMetadata,
    TrustedModelStore,
    canonical_json,
)

KEY_A = b"a" * 32
KEY_B = b"b" * 32


def _signer(key: bytes = KEY_A, key_id: str = "k1") -> ModelSigner:
    return ModelSigner(key, key_id)


def test_sign_verify_round_trip():
    signer = _signer()
    metadata = {"name": "m", "version": "3", "params": 7_000_000_000}
    envelope = signer.sign(metadata)
    assert envelope.key_id == "k1"
    assert envelope.algorithm == ALGORITHM
    assert signer.verify(envelope) == metadata


def test_canonical_json_is_deterministic():
    a = canonical_json({"b": 1, "a": [1, 2]})
    b = canonical_json({"a": [1, 2], "b": 1})
    assert a == b


def test_tampered_metadata_rejected():
    envelope = _signer().sign({"name": "m", "version": "1"})
    tampered = SignedMetadata(metadata={"name": "m", "version": "2"},
                              key_id=envelope.key_id,
                              signature=envelope.signature)
    with pytest.raises(SignatureVerificationFailed) as exc:
        _signer().verify(tampered)
    assert exc.value.code == "signature_verification_failed"
    assert exc.value.recoverable is False


def test_wrong_key_rejected():
    envelope = _signer(KEY_A, "k1").sign({"name": "m"})
    with pytest.raises(SignatureVerificationFailed):
        _signer(KEY_B, "k1").verify(envelope)


def test_unknown_key_id_fails_closed():
    envelope = _signer(KEY_A, "k1").sign({"name": "m"})
    other = SignedMetadata(metadata=envelope.metadata, key_id="ghost",
                           signature=envelope.signature)
    with pytest.raises(SignatureVerificationFailed, match="unknown key id"):
        _signer(KEY_A, "k1").verify(other)


def test_wrong_algorithm_rejected():
    envelope = _signer().sign({"name": "m"})
    forged = SignedMetadata(metadata=envelope.metadata,
                            key_id=envelope.key_id,
                            signature=envelope.signature,
                            algorithm="ROT13/hugrgate-v1")
    with pytest.raises(SignatureVerificationFailed, match="algorithm"):
        _signer().verify(forged)


def test_malformed_envelope_rejected():
    with pytest.raises(SignatureVerificationFailed):
        SignedMetadata.from_dict({"nope": True})
    with pytest.raises(SignatureVerificationFailed):
        SignedMetadata.from_json("not json {")
    with pytest.raises(SignatureVerificationFailed):
        SignedMetadata.from_json("[1, 2]")


def test_bad_key_size_rejected():
    with pytest.raises(ValueError):
        ModelSigner(b"short", "k1")


def test_sidecar_file_round_trip(tmp_path):
    signer = _signer()
    path = signer.write_signed({"name": "m", "version": "9"},
                               tmp_path / "model.sig")
    assert signer.read_signed(path) == {"name": "m", "version": "9"}
    # Tamper with the file bytes: verification must fail.
    text = path.read_text().replace('"version": "9"', '"version": "8"')
    path.write_text(text)
    with pytest.raises(SignatureVerificationFailed):
        signer.read_signed(path)


def test_trusted_store_refuses_unverified():
    store = TrustedModelStore({"k1": KEY_A})
    bad = _signer(KEY_B, "k1").sign({"name": "m"})
    with pytest.raises(SignatureVerificationFailed):
        store.register(bad)
    assert len(store) == 0


def test_trusted_store_serves_only_attested():
    store = TrustedModelStore({"k1": KEY_A})
    store.register(_signer().sign({"name": "m", "version": "1"}))
    assert store.get("m") == {"name": "m", "version": "1"}
    assert store.get("ghost") is None


def test_key_rotation_re_signs_store():
    store = TrustedModelStore({"k1": KEY_A})
    store.register(_signer().sign({"name": "m"}))
    assert store.rotate(KEY_B, "k2") == 1
    assert store.get("m") == {"name": "m"}
    # Old key no longer verifies anything in the store.
    with pytest.raises(SignatureVerificationFailed):
        store.register(_signer(KEY_A, "k1").sign({"name": "n"}))


def test_error_wire_round_trip():
    err = SignatureVerificationFailed("bad tag", key_id="k1")
    rebuilt = HugrGateError.from_dict(err.to_dict())
    assert isinstance(rebuilt, SignatureVerificationFailed)
