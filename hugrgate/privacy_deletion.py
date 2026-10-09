"""Secure deletion hooks. Slice 240.

Deleting a record should mean it is *gone* — not merely
unreferenced. This module provides:

- :func:`shred_bytes` — multi-pass overwrite of a ``bytearray``
  (zeros, ones, CSPRNG), plus :class:`SecureBuffer`, a context
  manager that shreds on exit. Secrets should live in
  ``bytearray``\\ s, never in immutable ``str`` (which cannot be
  overwritten).
- :class:`SecureDeleter` — a hook registry fired per deleted
  record: each hook runs, bytearray values in the record's metadata
  are shredded best-effort, and a :class:`DeletionReceipt` is
  returned as auditable proof of deletion.
- :class:`CryptoShredder` — for encrypted stores: dropping the
  data-encryption key cryptographically shreds everything sealed
  under it, without touching the ciphertext.

Honesty note: overwriting reduces a secret's lifetime in memory; it
cannot guarantee against copies the interpreter, OS paging, or
hardware already made. The receipt records what *was* done, not a
forensic guarantee. Encrypted-at-rest data + key destruction
(crypto-shredding) is the stronger primitive — prefer it for
high-sensitivity stores (slices 241-242).
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.provenance import DecisionRecord

__all__ = [
    "CryptoShredder",
    "DeletionReceipt",
    "SecureBuffer",
    "SecureDeleter",
    "shred_bytes",
]

#: Hook signature: called with the record being deleted, before removal.
DeletionHook = Callable[[DecisionRecord], None]


def shred_bytes(buffer: bytearray, passes: int = 3) -> None:
    """Overwrite a bytearray in place (zeros, ones, then random).

    Raises ``TypeError`` for non-bytearray input — immutable ``bytes``
    and ``str`` cannot be shredded; that is a caller bug, not a
    silent no-op.
    """
    if not isinstance(buffer, bytearray):
        raise TypeError(
            f"can only shred bytearray, got {type(buffer).__name__}; "
            f"keep secrets in bytearray, not str/bytes")
    if passes < 1:
        raise ValueError("passes must be >= 1")
    length = len(buffer)
    patterns = [b"\x00", b"\xff"]
    for i in range(passes):
        if i < len(patterns):
            buffer[:] = patterns[i] * length
        else:
            buffer[:] = secrets.token_bytes(length)
    buffer[:] = b"\x00" * length


class SecureBuffer:
    """Context manager holding a shred-on-exit bytearray.

    Usage::

        with SecureBuffer(b"secret") as buf:
            use(bytes(buf))
        # buf is shredded here, even on exception.
    """

    def __init__(self, initial: bytes | bytearray = b"",
                 passes: int = 3):
        self._buffer = bytearray(initial)
        self._passes = passes
        self._shredded = False

    def __enter__(self) -> bytearray:
        return self._buffer

    def __exit__(self, *exc: Any) -> None:
        self.shred()

    def shred(self) -> None:
        """Shred now; idempotent."""
        if not self._shredded:
            shred_bytes(self._buffer, passes=self._passes)
            self._shredded = True

    @property
    def shredded(self) -> bool:
        return self._shredded


def _shred_record_values(record: DecisionRecord) -> list[str]:
    """Best-effort shred of bytearray values in record metadata."""
    shredded: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, bytearray):
            shred_bytes(node)
            shredded.append(path)
        elif isinstance(node, Mapping):
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else str(key))
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}[{i}]")

    walk(record.metadata, "metadata")
    return shredded


@dataclass
class DeletionReceipt:
    """Auditable proof that a record was deleted."""

    record_hash: str
    timestamp: float = field(default_factory=time.time)
    hooks_fired: list[str] = field(default_factory=list)
    shredded_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"record_hash": self.record_hash,
                "timestamp": self.timestamp,
                "hooks_fired": list(self.hooks_fired),
                "shredded_fields": list(self.shredded_fields)}


class SecureDeleter:
    """Fires deletion hooks and shreds record secrets.

    Attach as ``on_purge`` to :func:`purge_expired
    <hugrgate.privacy_retention.purge_expired>`::

        deleter = SecureDeleter()
        deleter.register(my_audit_hook)
        purge_expired(store, policy, on_purge=deleter)
    """

    def __init__(self):
        self._hooks: list[tuple[str, DeletionHook]] = []

    def register(self, hook: DeletionHook, name: str = "") -> None:
        """Register a hook (name defaults to ``hook.__name__``)."""
        hook_name = name or getattr(hook, "__name__", type(hook).__name__)
        self._hooks.append((hook_name, hook))

    def unregister(self, name: str) -> bool:
        """Remove hooks by name; True when any were removed."""
        before = len(self._hooks)
        self._hooks = [(n, h) for n, h in self._hooks if n != name]
        return len(self._hooks) < before

    @property
    def hooks(self) -> list[str]:
        """Registered hook names."""
        return [name for name, _ in self._hooks]

    def __call__(self, record: DecisionRecord) -> DeletionReceipt:
        """Run hooks + shred; return the deletion receipt."""
        fired: list[str] = []
        for name, hook in self._hooks:
            hook(record)
            fired.append(name)
        shredded = _shred_record_values(record)
        return DeletionReceipt(record_hash=record.record_hash,
                               hooks_fired=fired,
                               shredded_fields=shredded)


class CryptoShredder:
    """Key-destruction based deletion for encrypted stores.

    Dropping a data-encryption key renders every ciphertext sealed
    under it permanently unreadable — deletion without touching the
    ciphertext. ``drop_key`` is typically a key-provider revocation
    (slice 243).
    """

    def __init__(self, drop_key: Callable[[str], None]):
        self._drop_key = drop_key
        self._shredded_keys: list[str] = []

    def shred_key(self, key_id: str) -> None:
        """Destroy a key; records the key id for audit."""
        self._drop_key(str(key_id))
        self._shredded_keys.append(str(key_id))

    @property
    def shredded_keys(self) -> list[str]:
        return list(self._shredded_keys)
