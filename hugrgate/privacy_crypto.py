"""Authenticated encryption (stdlib only) + encrypted cache. Slice 241.

No third-party crypto dependency: :class:`SealedBox` is an
encrypt-then-MAC construction from ``hashlib``/``hmac``/``secrets``:

- key derivation: HKDF-SHA256 (RFC 5869);
- encryption: HMAC-SHA256 in counter mode as a keystream (a
  well-studied PRF-based stream cipher), random 128-bit nonce per
  message;
- authentication: HMAC-SHA256 over ``domain || nonce || associated
  || ciphertext``; verification is constant-time and any tampering
  raises :class:`SealError`.

This is a deliberately small, auditable construction — not a
replacement for libsodium where available. The threat model:
protect cached decisions at rest from offline disk theft and from
cross-tenant reads in shared storage. It does not protect against
an attacker who already holds the key.

:class:`EncryptedDecisionCache` wraps :class:`DecisionCache`:
entries are pickled, sealed, and stored as opaque blobs. The
privacy-class cache rules still apply first (``strict`` /
``forbidden`` are never cached, sealed or not).
"""

from __future__ import annotations

import hashlib
import hmac
import pickle
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hugrgate.cache import DecisionCache, cache_key
from hugrgate.errors import SealError
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import PrivacyGuard
from hugrgate.privacy_retention import RetentionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "EncryptedDecisionCache",
    "SealedBox",
    "hkdf",
    "require_key",
]

_KEY_BYTES = 32
_NONCE_BYTES = 16
_TAG_BYTES = 32
_DOMAIN = b"hugrgate-seal-v1"


def hkdf(key: bytes, *, salt: bytes = b"", info: bytes = b"",
         length: int = 32) -> bytes:
    """HKDF-SHA256 (RFC 5869)."""
    if not key:
        raise ValueError("hkdf key must be non-empty")
    if length < 1 or length > 255 * 32:
        raise ValueError("hkdf length out of range")
    prk = hmac.new(salt or b"\x00" * 32, key, hashlib.sha256).digest()
    okm = b""
    previous = b""
    for counter in range(1, -(-length // 32) + 1):
        previous = hmac.new(
            prk, previous + info + bytes([counter]),
            hashlib.sha256).digest()
        okm += previous
    return okm[:length]


def require_key(key: bytes) -> bytes:
    """Validate a 32-byte key; return it as immutable bytes."""
    if not isinstance(key, (bytes, bytearray)) or len(key) != _KEY_BYTES:
        size = len(key) if isinstance(key, (bytes, bytearray)) else "?"
        raise ValueError(f"key must be {_KEY_BYTES} bytes, got {size}")
    return bytes(key)


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    stream = b""
    counter = 0
    while len(stream) < length:
        stream += hmac.new(
            key, nonce + counter.to_bytes(4, "big"),
            hashlib.sha256).digest()
        counter += 1
    return stream[:length]


def _xor(left: bytes, right: bytes) -> bytes:
    # Lengths are equal by construction; strict=True turns any
    # mismatch into a loud bug instead of silent truncation.
    return bytes(a ^ b for a, b in zip(left, right, strict=True))


class SealedBox:
    """Authenticated encryption: seal() / open()."""

    @staticmethod
    def seal(key: bytes, plaintext: bytes,
             associated: bytes = b"") -> bytes:
        """Seal ``plaintext``; returns ``nonce || ciphertext || tag``."""
        key = require_key(key)
        if not isinstance(plaintext, (bytes, bytearray)):
            raise TypeError("plaintext must be bytes")
        nonce = secrets.token_bytes(_NONCE_BYTES)
        ciphertext = _xor(bytes(plaintext),
                          _keystream(bytes(key), nonce, len(plaintext)))
        tag = hmac.new(bytes(key),
                       _DOMAIN + nonce + bytes(associated) + ciphertext,
                       hashlib.sha256).digest()
        return nonce + ciphertext + tag

    @staticmethod
    def open(key: bytes, blob: bytes,
             associated: bytes = b"") -> bytes:
        """Open a sealed blob; raises :class:`SealError` on tampering.

        Raises
        ------
        SealError
            Wrong key, truncated blob, or failed authentication —
            the blob must not be trusted.
        """
        key = require_key(key)
        if not isinstance(blob, (bytes, bytearray)):
            raise SealError("sealed blob must be bytes",
                            reason="type")
        blob = bytes(blob)
        if len(blob) < _NONCE_BYTES + _TAG_BYTES:
            raise SealError("sealed blob truncated", reason="truncated")
        nonce = blob[:_NONCE_BYTES]
        tag = blob[-_TAG_BYTES:]
        ciphertext = blob[_NONCE_BYTES:-_TAG_BYTES]
        expected = hmac.new(bytes(key),
                            _DOMAIN + nonce + bytes(associated) + ciphertext,
                            hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise SealError("authentication failed: wrong key or "
                            "tampered blob", reason="auth")
        return _xor(ciphertext, _keystream(bytes(key), nonce,
                                           len(ciphertext)))


@dataclass
class _SealedEntry:
    """Opaque sealed cache entry (never holds plaintext)."""

    blob: bytes
    namespace: str
    backend: str


class EncryptedDecisionCache(DecisionCache):
    """A :class:`DecisionCache` that seals entries at rest.

    Parameters
    ----------
    key:
        32-byte data-encryption key. Production keys come from a
        :class:`~hugrgate.privacy_keys.KeyProvider` (slice 243);
        pass raw bytes only for tests or single-process use.
    namespace:
        Binds sealed blobs to this cache instance (associated data).
    """

    def __init__(self, key: bytes, *, ttl_seconds: float = 300.0,
                 max_size: int = 1000, namespace: str = "decision-cache"):
        super().__init__(ttl_seconds=ttl_seconds, max_size=max_size)
        self._key = require_key(key)
        self._namespace = str(namespace)

    def _associated(self, state: Mapping[str, Any], spec: DecisionSpec,
                    policy: DecisionPolicy) -> bytes:
        return (self._namespace + ":" +
                cache_key(state, spec, policy)).encode()

    def put(self, state: Mapping[str, Any], spec: DecisionSpec,
            policy: DecisionPolicy, result: DecisionResult,
            retention: RetentionPolicy | None = None) -> bool:
        """Seal and store ``result``; False when privacy forbids caching."""
        if not PrivacyGuard.cache_allowed(policy):
            return False
        sealed = _SealedEntry(
            blob=SealedBox.seal(
                self._key, pickle.dumps(result),
                associated=self._associated(state, spec, policy)),
            namespace=self._namespace,
            backend=result.backend)
        return super().put(state, spec, policy, sealed,  # type: ignore[arg-type]
                           retention=retention)

    def _verify_entry(self, entry, state: Mapping[str, Any],
                      spec: DecisionSpec, policy: DecisionPolicy) -> None:
        """Authenticate the sealed blob before the integrity seal runs.

        A tampered blob must fail closed with ``SealError`` — the
        integrity checksum would otherwise silently evict the entry
        as corrupt and return a miss, hiding the tampering.
        """
        sealed = entry.result
        if not isinstance(sealed, _SealedEntry):
            raise SealError("cache entry is not sealed",
                            reason="unexpected-type")
        # Raises SealError on authentication failure.
        SealedBox.open(
            self._key, sealed.blob,
            associated=self._associated(state, spec, policy))

    def get(self, state: Mapping[str, Any], spec: DecisionSpec,
            policy: DecisionPolicy) -> DecisionResult | None:
        """Return the unsealed cached result, or None.

        Raises
        ------
        SealError
            The stored blob failed authentication — the cache was
            tampered with or the key changed. Fail closed: never
            return plaintext on auth failure.
        """
        sealed = super().get(state, spec, policy)
        if sealed is None:
            return None
        if not isinstance(sealed, _SealedEntry):
            raise SealError("cache entry is not sealed",
                            reason="unexpected-type")
        plaintext = SealedBox.open(
            self._key, sealed.blob,
            associated=self._associated(state, spec, policy))
        result = pickle.loads(plaintext)
        if not isinstance(result, DecisionResult):
            raise SealError("sealed payload is not a DecisionResult",
                            reason="unexpected-type")
        return result

    def key_id_hint(self) -> str:
        """Non-secret hint identifying the key (first 8 hex of its hash)."""
        return "key:" + hashlib.sha256(self._key).hexdigest()[:8]

    def __deepcopy__(self, memo: dict[int, Any]) -> EncryptedDecisionCache:
        # Never duplicate the key material through a generic deepcopy.
        raise TypeError("EncryptedDecisionCache cannot be deep-copied; "
                        "construct a new one with the same key")
