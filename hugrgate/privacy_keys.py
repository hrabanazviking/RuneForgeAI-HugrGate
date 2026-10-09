"""Key-provider abstraction. Slice 243.

Encryption is only as good as key management. :class:`KeyProvider`
is the interface every key consumer (encrypted cache, sealed
provenance, token vaults) uses; implementations:

- :class:`EnvKeyProvider` — 32-byte key from an environment
  variable (hex or base64);
- :class:`FileKeyProvider` — key from a file (hex, base64, or raw
  32 bytes; the file should be mode ``0o600`` — warn otherwise);
- :class:`EphemeralKeyProvider` — in-memory CSPRNG keys, generated
  on first use; gone when the process exits;
- :class:`RotatingKeyProvider` — a primary provider plus retired
  providers: encryption always uses the primary, decryption tries
  each in turn, so rotation never strands sealed data.

:func:`derive_key` derives per-context subkeys via HKDF, so one
master key safely serves many namespaces (cache vs provenance vs
token vault).
"""

from __future__ import annotations

import base64
import binascii
import os
import secrets
import stat
import warnings
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hugrgate.errors import KeyProviderError
from hugrgate.log import get_logger
from hugrgate.privacy_crypto import hkdf, require_key

if TYPE_CHECKING:
    # Deferred: privacy_crypto/provenance must not import this module.
    from hugrgate.privacy_crypto import EncryptedDecisionCache
    from hugrgate.privacy_provenance import SealedProvenanceStore

logger = get_logger(__name__)

__all__ = [
    "EnvKeyProvider",
    "EphemeralKeyProvider",
    "FileKeyProvider",
    "KeyProvider",
    "RotatingKeyProvider",
    "cache_from_provider",
    "derive_key",
    "provenance_store_from_provider",
]

_KEY_BYTES = 32


def _parse_key_material(raw: bytes | str, source: str) -> bytes:
    """Parse hex, base64, or raw 32-byte key material."""
    if isinstance(raw, bytes) and len(raw) == _KEY_BYTES:
        return raw
    try:
        text = raw.decode("ascii") if isinstance(raw, bytes) else raw
    except UnicodeDecodeError:
        text = ""
    compact = "".join(text.split())
    decoders = (lambda: bytes.fromhex(compact),
                lambda: base64.b64decode(compact, validate=True))
    for decode in decoders:
        try:
            candidate = decode()
        except (ValueError, binascii.Error):
            continue
        if len(candidate) == _KEY_BYTES:
            return candidate
    raise KeyProviderError(
        f"key material from {source} is not 32 bytes (tried hex, "
        f"base64, and raw)", source=source)


class KeyProvider(ABC):
    """Interface for key material sources."""

    @abstractmethod
    def get_key(self, key_id: str) -> bytes:
        """Return the 32-byte key for ``key_id`` (raises KeyProviderError)."""

    def key_ids(self) -> list[str]:
        """Known key ids (best effort; may be empty)."""
        return []

    def forget(self, key_id: str) -> bool:
        """Drop a key from memory; False when unsupported/unknown."""
        return False


class EnvKeyProvider(KeyProvider):
    """Keys from environment variables.

    ``key_id`` maps to an env var directly, or via ``prefix``:
    ``EnvKeyProvider(prefix="HUGR_")`` reads ``HUGR_<key_id>``.
    """

    def __init__(self, prefix: str = "", env: dict[str, str] | None = None):
        self.prefix = prefix
        self._env = env if env is not None else os.environ

    def _var(self, key_id: str) -> str:
        return f"{self.prefix}{key_id}"

    def get_key(self, key_id: str) -> bytes:
        var = self._var(key_id)
        raw = self._env.get(var)
        if raw is None:
            raise KeyProviderError(
                f"environment variable {var!r} is not set", key_id=key_id)
        return require_key(_parse_key_material(raw, f"env:{var}"))

    def key_ids(self) -> list[str]:
        if not self.prefix:
            return []
        return [name[len(self.prefix):] for name in self._env
                if name.startswith(self.prefix)]


class FileKeyProvider(KeyProvider):
    """Keys from files: ``<directory>/<key_id>.key``.

    Warns when the key file is group/world-readable.
    """

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def _path(self, key_id: str) -> Path:
        if "/" in key_id or key_id in (".", ".."):
            raise KeyProviderError(f"invalid key_id: {key_id!r}",
                                   key_id=key_id)
        return self.directory / f"{key_id}.key"

    def get_key(self, key_id: str) -> bytes:
        path = self._path(key_id)
        try:
            raw = path.read_bytes()
        except OSError as e:
            raise KeyProviderError(
                f"cannot read key file {path}: {e}", key_id=key_id) from e
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            warnings.warn(f"key file {path} is group/world-readable "
                          f"(mode {oct(mode)}); use 0o600",
                          stacklevel=2)
        return require_key(_parse_key_material(raw, f"file:{path}"))

    def key_ids(self) -> list[str]:
        if not self.directory.is_dir():
            return []
        return sorted(p.stem for p in self.directory.glob("*.key"))


class EphemeralKeyProvider(KeyProvider):
    """In-memory CSPRNG keys; generated lazily, forgotten on exit."""

    def __init__(self):
        self._keys: dict[str, bytes] = {}

    def get_key(self, key_id: str) -> bytes:
        key_id = str(key_id)
        if key_id not in self._keys:
            self._keys[key_id] = secrets.token_bytes(_KEY_BYTES)
            logger.debug("keys: generated ephemeral key %r", key_id)
        return self._keys[key_id]

    def key_ids(self) -> list[str]:
        return sorted(self._keys)

    def forget(self, key_id: str) -> bool:
        if str(key_id) in self._keys:
            del self._keys[str(key_id)]
            return True
        return False


class RotatingKeyProvider(KeyProvider):
    """Primary + retired providers for seamless key rotation.

    Encryption uses the primary; decryption tries every provider in
    order, so data sealed under a retired key still opens after
    rotation. :meth:`decrypt_with_any` is the decryption entry point.
    """

    def __init__(self, primary: KeyProvider,
                 retired: list[KeyProvider] | None = None):
        self.primary = primary
        self.retired = list(retired or [])

    def get_key(self, key_id: str) -> bytes:
        return self.primary.get_key(key_id)

    def key_ids(self) -> list[str]:
        ids = list(self.primary.key_ids())
        for provider in self.retired:
            for key_id in provider.key_ids():
                if key_id not in ids:
                    ids.append(key_id)
        return ids

    def retire_primary(self, new_primary: KeyProvider) -> None:
        """Rotate: the old primary becomes the newest retired key."""
        self.retired.insert(0, self.primary)
        self.primary = new_primary
        logger.info("keys: rotated primary key provider")

    def get_key_any(self, key_id: str) -> bytes:
        """First key that works, primary first (for decryption)."""
        errors: list[str] = []
        for provider in [self.primary, *self.retired]:
            try:
                return provider.get_key(key_id)
            except KeyProviderError as e:
                errors.append(str(e))
        raise KeyProviderError(
            f"no provider could supply key {key_id!r}: "
            + "; ".join(errors), key_id=key_id)


def derive_key(provider: KeyProvider, key_id: str, context: str,
               length: int = 32) -> bytes:
    """Derive a per-context subkey via HKDF (domain-separated)."""
    master = provider.get_key(key_id)
    return hkdf(master, salt=b"hugrgate-key-derive",
                info=f"ctx:{context}".encode(), length=length)


def cache_from_provider(provider: KeyProvider, key_id: str,
                        **kwargs: Any) -> EncryptedDecisionCache:
    """Build an :class:`EncryptedDecisionCache` from a key provider.

    The cache key is derived per-context (``"decision-cache"``), so
    one master key safely serves many consumers.
    """
    from hugrgate.privacy_crypto import EncryptedDecisionCache
    return EncryptedDecisionCache(
        derive_key(provider, key_id, "decision-cache"), **kwargs)


def provenance_store_from_provider(
        provider: KeyProvider, key_id: str,
        **kwargs: Any) -> SealedProvenanceStore:
    """Build a :class:`SealedProvenanceStore` from a key provider."""
    from hugrgate.privacy_provenance import SealedProvenanceStore
    return SealedProvenanceStore(
        derive_key(provider, key_id, "provenance"), **kwargs)
