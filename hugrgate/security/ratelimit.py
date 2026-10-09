"""Per-key rate limiting. Slice 420.

Threat T-13: an unauthenticated client floods ``/decide`` and
starves legitimate users. The runtime already had a thread-safe
:class:`~hugrgate.backpressure.TokenBucket`, but no per-caller
management — one global bucket cannot tell a flood from a crowd,
and a naive per-key dict is itself a memory-exhaustion vector
(the slice-418 attack class).

:class:`RateLimiter` keeps one token bucket per caller key (API
key id, IP, or ``"anonymous"``):

- per-tier rates: ``"anonymous"`` callers get the harshest
  budget, authenticated tiers get more; overrides per call;
- the key table is bounded: idle buckets are evicted past
  ``max_keys`` (LRU), so a key-spoofing flood cannot grow memory
  without bound;
- exceeding the limit raises :class:`RateLimitExceeded` (carrying
  ``retry_after_ms``) — recoverable, unlike the other security
  errors, because "try again later" is the correct response.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from hugrgate.backpressure import TokenBucket
from hugrgate.errors import RateLimitExceeded

__all__ = [
    "RateLimiter",
]


@dataclass
class _Tier:
    capacity: int
    refill_per_second: float


@dataclass
class _BucketEntry:
    bucket: TokenBucket
    last_seen: float


class RateLimiter:
    """Per-key token-bucket rate limiter with bounded key state."""

    #: The key used when the caller presents no credential. Gets the
    #: harshest default tier — T-13 is specifically about
    #: credential-less flooding.
    ANONYMOUS = "anonymous"

    def __init__(self, capacity: int = 10,
                 refill_per_second: float = 1.0,
                 max_keys: int = 100_000,
                 idle_ttl_seconds: float = 600.0) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        if refill_per_second <= 0:
            raise ValueError("refill_per_second must be > 0")
        if max_keys < 1:
            raise ValueError("max_keys must be >= 1")
        self._default = _Tier(capacity, float(refill_per_second))
        self._tiers: dict[str, _Tier] = {
            self.ANONYMOUS: _Tier(max(1, capacity // 10),
                                  max(0.1, refill_per_second / 10)),
        }
        self._max_keys = max_keys
        self._idle_ttl = idle_ttl_seconds
        self._buckets: OrderedDict[tuple[str, str], _BucketEntry] = (
            OrderedDict()
        )
        self._lock = threading.Lock()
        self._rejected = 0

    def set_tier(self, tier: str, capacity: int,
                 refill_per_second: float) -> None:
        """Register a named rate tier (e.g. ``"operator"``)."""
        if capacity < 1 or refill_per_second <= 0:
            raise ValueError("tier rates must be positive")
        self._tiers[tier] = _Tier(capacity, float(refill_per_second))

    def _bucket_for(self, key: str, tier: str | None) -> TokenBucket:
        # Buckets are keyed by (key, tier): a caller whose tier
        # changes (e.g. anonymous -> authenticated) gets the new
        # tier's budget instead of inheriting the old bucket.
        table_key = (key, tier or "")
        now = time.monotonic()
        entry = self._buckets.get(table_key)
        if entry is None:
            spec = self._tiers.get(tier or "", self._default)
            entry = _BucketEntry(
                TokenBucket(spec.capacity, spec.refill_per_second),
                now)
            self._buckets[table_key] = entry
        entry.last_seen = now
        self._buckets.move_to_end(table_key)
        # Bound the table: evict the stalest idle buckets first.
        while len(self._buckets) > self._max_keys:
            oldest_key = next(iter(self._buckets))
            if now - self._buckets[oldest_key].last_seen < self._idle_ttl:
                break
            del self._buckets[oldest_key]
        # Hard cap even when nothing is idle: LRU eviction.
        while len(self._buckets) > self._max_keys:
            self._buckets.popitem(last=False)
        return entry.bucket

    def throttle(self, key: str, n: int = 1,
                 tier: str | None = None) -> None:
        """Consume ``n`` tokens for ``key``; raise when the bucket is dry.

        ``key`` is the caller identity (API key id, IP, ...);
        use :attr:`ANONYMOUS` for credential-less callers.
        """
        if not key:
            raise ValueError("throttle key must be non-empty")
        if n < 1:
            raise ValueError("n must be >= 1")
        with self._lock:
            bucket = self._bucket_for(key, tier)
            if bucket.take(n):
                return
            retry_after_ms = bucket.retry_after_s(n) * 1000.0
            self._rejected += 1
        raise RateLimitExceeded(
            f"rate limit exceeded for {key!r}",
            reason="rate_limited", key=key,
            retry_after_ms=round(retry_after_ms, 1))

    def stats(self, key: str | None = None) -> dict[str, Any]:
        with self._lock:
            out: dict[str, Any] = {
                "tracked_keys": len(self._buckets),
                "rejected": self._rejected,
                "max_keys": self._max_keys,
            }
            if key is not None:
                matches = [entry for (k, _), entry in self._buckets.items()
                           if k == key]
                if matches:
                    out["available"] = round(
                        min(e.bucket.available for e in matches), 3)
            return out
