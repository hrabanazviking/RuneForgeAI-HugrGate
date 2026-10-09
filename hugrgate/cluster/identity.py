"""Node identity — stable, unforgeable node ids. Slice 202.

A node's identity is a 256-bit secret generated once and persisted with
owner-only permissions. The public node id is ``sha256(secret)``: stable
across restarts (same key file → same id), unforgeable without the key
file, and never transmitted in full — peers see only the id, never the
secret. Slice 208 (mutual authentication) builds on this by proving
possession of the secret via challenge-response.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from typing import Any

from hugrgate.cluster.protocol import PROTOCOL_VERSION
from hugrgate.errors import SpecError

__all__ = [
    "KEY_BYTES",
    "NodeIdentity",
]

#: 256-bit node secret.
KEY_BYTES = 32


@dataclass
class NodeIdentity:
    """A node's long-lived identity.

    ``key`` is the 256-bit secret; ``node_id`` derives from it and is
    the node's public name on the wire. The secret never leaves the
    node — it is only proven via challenge-response (slice 208).
    """

    key: bytes
    display_name: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.key, bytes) or len(self.key) != KEY_BYTES:
            raise SpecError(
                f"node key must be {KEY_BYTES} bytes, got "
                f"{len(self.key) if isinstance(self.key, bytes) else type(self.key).__name__}")
        if not isinstance(self.display_name, str):
            raise SpecError("display_name must be a string")

    @classmethod
    def generate(cls, display_name: str = "") -> NodeIdentity:
        """Mint a fresh identity from the OS CSPRNG."""
        return cls(key=secrets.token_bytes(KEY_BYTES),
                   display_name=display_name)

    @property
    def node_id(self) -> str:
        """Public node id: sha256(secret), 64 lowercase hex chars."""
        return hashlib.sha256(self.key).hexdigest()

    def to_advertisement(self) -> dict[str, Any]:
        """Public face shown to peers (never includes the secret)."""
        return {
            "node_id": self.node_id,
            "display_name": self.display_name,
            "protocol_version": PROTOCOL_VERSION,
        }

    def save(self, path: str | os.PathLike[str]) -> None:
        """Persist the identity with owner-only (0600) permissions.

        The file is created with ``os.open(..., 0o600)`` so the secret
        is never briefly world-readable — a plain ``open()`` + chmod
        would leave a race window.
        """
        payload = json.dumps({
            "key": self.key.hex(),
            "display_name": self.display_name,
        }).encode("utf-8")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(payload)
        except BaseException:
            # os.fdopen took ownership on success; on failure before that,
            # the raw fd would leak — close it explicitly.
            try:
                os.close(fd)
            except OSError:  # already closed by fdopen's failure path
                pass
            raise

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> NodeIdentity:
        """Load a persisted identity; raises :class:`SpecError` if the
        file is missing, unreadable, or malformed."""
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            raise SpecError(f"node identity file not found: {path}") from None
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
            raise SpecError(
                f"node identity file {path} is unreadable: {e}") from e
        if not isinstance(data, dict):
            raise SpecError(
                f"node identity file {path} must hold a JSON object")
        raw_key = data.get("key")
        if not isinstance(raw_key, str):
            raise SpecError(
                f"node identity file {path} has no hex 'key' field")
        try:
            key = bytes.fromhex(raw_key)
        except ValueError:
            raise SpecError(
                f"node identity file {path} has a malformed key") from None
        display = data.get("display_name", "")
        if not isinstance(display, str):
            raise SpecError(
                f"node identity file {path} has a non-string display_name")
        return cls(key=key, display_name=display)
