"""Mutual authentication for cluster RPC. Slice 208.

Every node holds the same 256-bit pre-shared :class:`ClusterKey`
(distributed out of band by the operator). Each RPC envelope's exact
wire bytes are sealed with HMAC-SHA256 and the tag travels in the
``X-Cluster-MAC`` HTTP header — the envelope itself stays clean, and a
forged or tampered message fails closed.

This is *mutual*: the client proves key possession on every request,
the server on every response (the client's ``mac_provider`` verifies
nothing, but the server's reply tag lets a client-side verifier do the
same — wire it where you need it).

Replay protection: when ``require_auth`` is on, the node tracks the
highest ``seq`` seen per sender and rejects anything at or below it —
a captured envelope cannot be re-fired.

Key files live at 0600, same as node identity keys (slice 202).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from hugrgate.errors import SpecError

if TYPE_CHECKING:
    from hugrgate.cluster.node import ClusterNode

__all__ = [
    "AUTH_HEADER",
    "KEY_BYTES",
    "Authenticator",
    "ClusterKey",
    "enable_mutual_auth",
]

#: HTTP header carrying the HMAC tag of the envelope bytes.
AUTH_HEADER = "x-cluster-mac"

#: 256-bit pre-shared key.
KEY_BYTES = 32


@dataclass
class ClusterKey:
    """The cluster's pre-shared secret."""

    key: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.key, bytes) or len(self.key) != KEY_BYTES:
            raise SpecError(
                f"cluster key must be {KEY_BYTES} bytes")

    @classmethod
    def generate(cls) -> ClusterKey:
        return cls(key=secrets.token_bytes(KEY_BYTES))

    def save(self, path: str | os.PathLike[str]) -> None:
        """Persist with owner-only (0600) permissions, no race window."""
        payload = json.dumps({"key": self.key.hex()}).encode("utf-8")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(payload)
        except BaseException:
            try:
                os.close(fd)
            except OSError:  # already closed by fdopen's failure path
                pass
            raise

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> ClusterKey:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            raise SpecError(
                f"cluster key file not found: {path}") from None
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
            raise SpecError(
                f"cluster key file {path} is unreadable: {e}") from e
        if not isinstance(data, dict) or not isinstance(
                data.get("key"), str):
            raise SpecError(
                f"cluster key file {path} must hold "
                f'{{"key": "<64-hex>"}}')
        try:
            key = bytes.fromhex(data["key"])
        except ValueError:
            raise SpecError(
                f"cluster key file {path} has a malformed key") from None
        return cls(key=key)


class Authenticator:
    """HMAC-SHA256 seal/verify over exact wire bytes."""

    def __init__(self, key: ClusterKey) -> None:
        if not isinstance(key, ClusterKey):
            raise SpecError(
                f"key must be a ClusterKey, got {type(key).__name__}")
        self._key = key

    def seal(self, data: bytes) -> str:
        """Hex tag for ``data``."""
        if not isinstance(data, (bytes, bytearray)):
            raise SpecError("seal() needs bytes")
        return hmac.new(self._key.key, bytes(data),
                        hashlib.sha256).hexdigest()

    def verify(self, data: bytes, tag: str | None) -> bool:
        """Constant-time verification. Never raises on bad input —
        a bad tag is ``False``, not an exception."""
        if not isinstance(tag, str):
            return False
        try:
            presented = bytes.fromhex(tag)
        except ValueError:
            return False
        expected = hmac.new(self._key.key, bytes(data),
                            hashlib.sha256).digest()
        return hmac.compare_digest(presented, expected)


def enable_mutual_auth(node: ClusterNode, key: ClusterKey
                       ) -> Callable[[bytes], str]:
    """Switch a node (and its RPC client) to authenticated mode.

    Sets ``node.authenticator`` + ``node.require_auth``, and returns a
    ``mac_provider`` to hand to :class:`RPCClient`::

        provider = enable_mutual_auth(node, key)
        node.rpc = RPCClient(node.node_id, mac_provider=provider)

    Both directions are then sealed: requests carry ``X-Cluster-MAC``,
    and the node verifies every inbound envelope (plus replay).
    """
    authenticator = Authenticator(key)
    node.authenticator = authenticator
    node.require_auth = True

    def mac_provider(data: bytes) -> str:
        return authenticator.seal(data)

    return mac_provider
