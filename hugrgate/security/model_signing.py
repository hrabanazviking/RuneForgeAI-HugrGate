"""Signed model metadata. Slice 405.

Model metadata (identity, version, capability claims, checksums) is a
trust decision: the gate routes, caches, and explains based on it.
An unsigned metadata file can be edited to misroute decisions
(threat T-02). This module makes metadata tamper-evident:

- :class:`ModelSigner` — HMAC-SHA256 sign/verify over canonical
  JSON (stdlib only; keys validated by
  :func:`hugrgate.privacy_crypto.require_key`).
- :class:`SignedMetadata` — the envelope: metadata dict, key id,
  algorithm tag, hex signature; JSON-serializable for sidecar
  ``.sig`` files.
- :class:`TrustedModelStore` — verify-before-trust registry:
  ``register()`` refuses envelopes that do not verify, so only
  attested metadata is ever served.

Key rotation is first-class: verification uses a ``key_id ->
key`` map, unknown key ids fail closed, and ``rotate()`` re-signs
the store's envelopes under a new key.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hugrgate.errors import SignatureVerificationFailed

__all__ = [
    "ALGORITHM",
    "ModelSigner",
    "SignedMetadata",
    "TrustedModelStore",
    "canonical_json",
]

#: Algorithm tag pinned into every envelope.
ALGORITHM = "HMAC-SHA256/hugrgate-metadata-v1"


def _require_key(key: bytes) -> bytes:
    """Validate a 32-byte key.

    Imported lazily: :mod:`hugrgate.privacy_crypto` imports
    :mod:`hugrgate.security.serde_guards`, so an eager import here
    would close a runtime import cycle through the ``security``
    package ``__init__``.
    """
    from hugrgate.privacy_crypto import require_key
    return require_key(key)


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    """Deterministic byte rendering of a metadata mapping."""
    return json.dumps(dict(payload), sort_keys=True,
                      separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


@dataclass(frozen=True)
class SignedMetadata:
    """A metadata envelope with its authentication tag."""

    metadata: dict[str, Any]
    key_id: str
    signature: str  # hex HMAC-SHA256
    algorithm: str = ALGORITHM
    signed_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": dict(self.metadata),
            "key_id": self.key_id,
            "signature": self.signature,
            "algorithm": self.algorithm,
            "signed_at": self.signed_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SignedMetadata:
        try:
            return cls(
                metadata=dict(data["metadata"]),
                key_id=str(data["key_id"]),
                signature=str(data["signature"]),
                algorithm=str(data.get("algorithm", ALGORITHM)),
                signed_at=float(data.get("signed_at", 0.0)),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise SignatureVerificationFailed(
                f"malformed signature envelope: {e}") from e

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> SignedMetadata:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise SignatureVerificationFailed(
                f"envelope is not valid JSON: {e}") from e
        if not isinstance(data, dict):
            raise SignatureVerificationFailed(
                "envelope must be a JSON object")
        return cls.from_dict(data)


class ModelSigner:
    """Signs and verifies model metadata with a named key."""

    def __init__(self, key: bytes, key_id: str) -> None:
        self._key = _require_key(key)
        if not key_id or not isinstance(key_id, str):
            raise ValueError("key_id must be a non-empty string")
        self._key_id = key_id

    @property
    def key_id(self) -> str:
        return self._key_id

    def _tag(self, metadata: Mapping[str, Any]) -> str:
        body = canonical_json(metadata)
        return hmac.new(self._key, ALGORITHM.encode() + b"\x00" + body,
                        hashlib.sha256).hexdigest()

    def sign(self, metadata: Mapping[str, Any]) -> SignedMetadata:
        """Authenticate ``metadata``; returns the signed envelope."""
        if not isinstance(metadata, Mapping):
            raise ValueError("metadata must be a mapping")
        return SignedMetadata(metadata=dict(metadata),
                              key_id=self._key_id,
                              signature=self._tag(metadata))

    def verify(self, envelope: SignedMetadata,
               keys: Mapping[str, bytes] | None = None) -> dict[str, Any]:
        """Return the metadata if the envelope verifies; else raise.

        ``keys`` maps key ids to keys for multi-key verification
        (rotation); defaults to this signer's own key.
        """
        keyring = {self._key_id: self._key} if keys is None else dict(keys)
        if envelope.algorithm != ALGORITHM:
            raise SignatureVerificationFailed(
                f"unsupported algorithm {envelope.algorithm!r}",
                key_id=envelope.key_id)
        raw = keyring.get(envelope.key_id)
        if raw is None:
            raise SignatureVerificationFailed(
                f"unknown key id {envelope.key_id!r}",
                key_id=envelope.key_id)
        key = _require_key(raw)
        expected = hmac.new(key, ALGORITHM.encode() + b"\x00"
                            + canonical_json(envelope.metadata),
                            hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, envelope.signature):
            raise SignatureVerificationFailed(
                "signature mismatch: metadata was altered or the key "
                "is wrong",
                key_id=envelope.key_id)
        return dict(envelope.metadata)

    def write_signed(self, metadata: Mapping[str, Any],
                     path: str | Path) -> Path:
        """Write the signed envelope as JSON next to the artifact."""
        path = Path(path)
        path.write_text(self.sign(metadata).to_json(), encoding="utf-8")
        return path

    def read_signed(self, path: str | Path,
                    keys: Mapping[str, bytes] | None = None
                    ) -> dict[str, Any]:
        """Read a sidecar envelope and verify it before trusting."""
        return self.verify(SignedMetadata.from_json(
            Path(path).read_text(encoding="utf-8")), keys)


class TrustedModelStore:
    """Verify-before-trust registry for model metadata.

    Only envelopes that verify against the keyring are stored;
    :meth:`get` therefore never serves unattested metadata.
    """

    def __init__(self, keys: Mapping[str, bytes]) -> None:
        if not keys:
            raise ValueError("TrustedModelStore needs at least one key")
        self._keys = {kid: _require_key(k) for kid, k in keys.items()}
        self._store: dict[str, SignedMetadata] = {}
        self._verifier = ModelSigner(next(iter(self._keys.values())),
                                    next(iter(self._keys)))

    def register(self, envelope: SignedMetadata) -> dict[str, Any]:
        """Verify and store; raises SignatureVerificationFailed if bad."""
        metadata = self._verifier.verify(envelope, self._keys)
        name = str(metadata.get("name") or metadata.get("model") or "?")
        self._store[name] = envelope
        return metadata

    def get(self, name: str) -> dict[str, Any] | None:
        envelope = self._store.get(name)
        if envelope is None:
            return None
        # Re-verify on every read: stored bytes are not trusted.
        return self._verifier.verify(envelope, self._keys)

    def rotate(self, new_key: bytes, new_key_id: str) -> int:
        """Re-sign every envelope under a new key; returns count."""
        signer = ModelSigner(new_key, new_key_id)
        for name, envelope in list(self._store.items()):
            metadata = self._verifier.verify(envelope, self._keys)
            self._store[name] = signer.sign(metadata)
        self._keys = {new_key_id: _require_key(new_key)}
        self._verifier = signer
        return len(self._store)

    def __len__(self) -> int:
        return len(self._store)
