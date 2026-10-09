"""Replay attack defenses. Slice 418.

Attack analysis of the existing cluster mechanism
(``ClusterNode._last_seq``, slice 208): the per-sender sequence
window stops naive replays, but the sender map grew without bound
(a sender-id flood was a memory-exhaustion vector — now an LRU
with a 4096 cap in ``hugrgate/cluster/node.py``), and there is no
timestamp/freshness binding: a delayed-but-fresh-seq message is
accepted.

This module is the generalized defense for new integrations:

- :class:`ReplayGuard` — nonce + timestamp window: duplicate
  nonces rejected, timestamps outside ``[now - max_age, now +
  max_skew]`` rejected, seen-nonces store bounded (LRU) and
  expired entries purged, thread-safe.
- :func:`seal_request` / :func:`open_request` — HMAC-signed
  envelopes carrying ``(payload, nonce, timestamp, key_id)``;
  opening verifies the tag (constant-time), the key id, and
  freshness through the guard, in that order.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import ReplayDetected

# NOTE (slice 418): ``hugrgate.privacy_crypto`` imports
# ``hugrgate.security.serde_guards`` at module top, so importing
# ``require_key`` here would be circular (the security -> privacy_crypto
# edge is forbidden at import time). Resolved lazily instead.

__all__ = [
    "ReplayGuard",
    "open_request",
    "seal_request",
]


def _require_key(key: bytes) -> bytes:
    from hugrgate.privacy_crypto import require_key
    return require_key(key)


class ReplayGuard:
    """Nonce + timestamp replay window.

    Remembers nonces for ``max_age_seconds``; a repeated nonce, a
    timestamp older than the window, or a timestamp too far in the
    future all raise :class:`ReplayDetected`. The store is bounded
    (LRU eviction past ``max_entries``) and expired nonces are
    purged on every check, so a nonce flood cannot grow memory
    without bound.
    """

    def __init__(self, max_age_seconds: float = 300.0,
                 max_skew_seconds: float = 60.0,
                 max_entries: int = 100_000) -> None:
        if max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be positive")
        if max_skew_seconds < 0:
            raise ValueError("max_skew_seconds must be >= 0")
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._max_age = max_age_seconds
        self._max_skew = max_skew_seconds
        self._max_entries = max_entries
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._lock = threading.Lock()
        self._rejected = 0

    def check(self, nonce: str,
              timestamp: float | None = None) -> None:
        """Accept a (nonce, timestamp) pair once; raise on replay/staleness."""
        if not nonce or not isinstance(nonce, str):
            raise ReplayDetected("empty or non-string nonce",
                                 reason="bad_nonce")
        now = time.time()
        moment = now if timestamp is None else timestamp
        if moment < now - self._max_age:
            raise ReplayDetected(
                f"stale timestamp: {moment} is older than "
                f"{self._max_age}s", reason="stale")
        if moment > now + self._max_skew:
            raise ReplayDetected(
                f"timestamp too far in the future: {moment}",
                reason="future_skew")
        with self._lock:
            self._purge_locked(now)
            if nonce in self._seen:
                self._rejected += 1
                raise ReplayDetected("nonce already seen: replay",
                                     reason="replay", nonce=nonce[:16])
            self._seen[nonce] = moment
            while len(self._seen) > self._max_entries:
                self._seen.popitem(last=False)

    def _purge_locked(self, now: float) -> None:
        cutoff = now - self._max_age
        # OrderedDict is insertion-ordered; stop at the first live entry.
        while self._seen:
            oldest_nonce = next(iter(self._seen))
            if self._seen[oldest_nonce] >= cutoff:
                break
            del self._seen[oldest_nonce]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "tracked_nonces": len(self._seen),
                "rejected": self._rejected,
                "max_age_seconds": self._max_age,
                "max_entries": self._max_entries,
            }


def _tag(key: bytes, nonce: str, timestamp: float,
         payload_bytes: bytes) -> str:
    return hmac.new(
        key,
        b"|".join([nonce.encode(), repr(timestamp).encode(),
                   payload_bytes]),
        hashlib.sha256).hexdigest()


@dataclass
class _Envelope:
    payload: dict[str, Any]
    nonce: str
    timestamp: float
    key_id: str
    tag: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "payload": dict(self.payload),
            "nonce": self.nonce,
            "timestamp": self.timestamp,
            "key_id": self.key_id,
            "tag": self.tag,
        }


def seal_request(payload: Mapping[str, Any], key: bytes,
                 key_id: str) -> dict[str, Any]:
    """Build a signed, replay-resistant request envelope."""
    raw_key = _require_key(key)
    if not key_id:
        raise ValueError("key_id must be non-empty")
    payload_bytes = json.dumps(dict(payload), sort_keys=True,
                               separators=(",", ":")).encode()
    nonce = secrets.token_hex(16)
    timestamp = time.time()
    return _Envelope(
        payload=dict(payload), nonce=nonce, timestamp=timestamp,
        key_id=key_id,
        tag=_tag(raw_key, nonce, timestamp, payload_bytes)).to_dict()


def open_request(envelope: Mapping[str, Any], keys: Mapping[str, bytes],
                 guard: ReplayGuard) -> dict[str, Any]:
    """Verify signature, key id, and freshness; return the payload.

    Order matters: the tag is checked before the guard, so
    unauthenticated input never pollutes the nonce store.
    """
    try:
        payload = dict(envelope["payload"])
        nonce = str(envelope["nonce"])
        timestamp = float(envelope["timestamp"])
        key_id = str(envelope["key_id"])
        tag = str(envelope["tag"])
    except (KeyError, TypeError, ValueError) as e:
        raise ReplayDetected(
            f"malformed envelope: {e}") from e
    raw = keys.get(key_id)
    if raw is None:
        raise ReplayDetected(f"unknown key id {key_id!r}",
                             reason="unknown_key")
    key = _require_key(raw)
    payload_bytes = json.dumps(payload, sort_keys=True,
                               separators=(",", ":")).encode()
    expected = _tag(key, nonce, timestamp, payload_bytes)
    if not hmac.compare_digest(expected, tag):
        raise ReplayDetected("envelope tag mismatch: tampered or wrong key",
                             reason="bad_tag")
    guard.check(nonce, timestamp)
    return payload
