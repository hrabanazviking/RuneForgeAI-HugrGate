"""Decision cache — request-hash keyed result memoization. Slice 38.

:class:`DecisionCache` maps a hash of ``(state, spec, policy)`` to the
:class:`DecisionResult`, with TTL expiry, LRU eviction at ``max_size``,
and two safety rails:

- **Privacy-aware**: entries are never stored for (or served to) decisions
  whose ``privacy_class`` forbids retention (``"strict"``) — see
  :class:`hugrgate.privacy.PrivacyGuard`.
- **Invalidation on model change**: :meth:`invalidate_backend` drops every
  entry produced by a backend, so a retrained model can never serve stale
  decisions.

Results are deep-copied on the way in and out so callers cannot mutate the
cached copy.
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hugrgate.log import get_logger
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import PrivacyGuard
from hugrgate.privacy_retention import RetentionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "DecisionCache",
    "cache_key",
]

logger = get_logger(__name__)


def _policy_fingerprint(policy: DecisionPolicy) -> dict[str, Any]:
    """The policy fields that can change a decision outcome."""
    return {
        "minimum_probability": policy.minimum_probability,
        "maximum_latency_ms": policy.maximum_latency_ms,
        "remote_inference": policy.remote_inference,
        "allowed_backends": policy.allowed_backends,
        "preferred_backends": policy.preferred_backends,
        "fallback_behavior": policy.fallback_behavior,
        "privacy_class": policy.privacy_class,
        "max_cost": policy.max_cost,
        "review_band": list(policy.review_band)
        if policy.review_band else None,
    }


def cache_key(state: Mapping[str, Any], spec: DecisionSpec,
              policy: DecisionPolicy) -> str:
    """Stable hash identifying one cacheable decision request."""
    payload = json.dumps(
        {"state": dict(state),
         "spec": spec.to_dict(),
         "policy": _policy_fingerprint(policy)},
        sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class _Entry:
    result: DecisionResult
    expires_at: float  # monotonic seconds
    backend: str


class DecisionCache:
    """TTL + LRU + privacy-aware cache of decision results."""

    def __init__(self, ttl_seconds: float = 300.0, max_size: int = 1000):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self.hits = 0
        self.misses = 0
        # RLock: stats() calls len(self), which also takes the lock.
        self._lock = threading.RLock()

    # -- core API ----------------------------------------------------------

    def get(self, state: Mapping[str, Any], spec: DecisionSpec,
            policy: DecisionPolicy) -> DecisionResult | None:
        """Return the cached result, or None on miss/expiry/privacy."""
        with self._lock:
            return self._get_locked(state, spec, policy)

    def _get_locked(self, state: Mapping[str, Any], spec: DecisionSpec,
                    policy: DecisionPolicy) -> DecisionResult | None:
        if not PrivacyGuard.cache_allowed(policy):
            return None
        key = cache_key(state, spec, policy)
        entry = self._entries.get(key)
        if entry is None:
            self.misses += 1
            logger.debug("cache miss (no entry)")
            return None
        if entry.expires_at <= time.monotonic():
            del self._entries[key]
            self.misses += 1
            logger.debug("cache miss (expired)")
            return None
        self._entries.move_to_end(key)  # LRU touch
        self.hits += 1
        logger.debug("cache hit")
        return copy.deepcopy(entry.result)

    def put(self, state: Mapping[str, Any], spec: DecisionSpec,
            policy: DecisionPolicy, result: DecisionResult,
            retention: RetentionPolicy | None = None) -> bool:
        """Store ``result``. Returns False when privacy forbids caching.

        When ``retention`` is given, the entry TTL is capped by the
        privacy class's maximum age (slice 239).
        """
        with self._lock:
            if not PrivacyGuard.cache_allowed(policy):
                return False
            key = cache_key(state, spec, policy)
            now = time.monotonic()
            ttl = retention.cache_ttl_for(policy, self.ttl_seconds) \
                if retention is not None else self.ttl_seconds
            self._entries[key] = _Entry(
                result=copy.deepcopy(result),
                expires_at=now + ttl,
                backend=result.backend)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_size:
                self._entries.popitem(last=False)  # evict least-recently-used
            return True

    # -- invalidation ------------------------------------------------------

    def invalidate_backend(self, backend_name: str) -> int:
        """Drop every entry produced by ``backend_name`` (model changed)."""
        with self._lock:
            doomed = [k for k, e in self._entries.items()
                      if e.backend == backend_name]
            for k in doomed:
                del self._entries[k]
            return len(doomed)

    def invalidate_model(self, backend_name: str,
                         model_version: str | None = None) -> int:
        """Alias: a new model version invalidates the backend's entries."""
        return self.invalidate_backend(backend_name)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    # -- introspection -----------------------------------------------------

    def __len__(self) -> int:
        # Opportunistically sweep expired entries on size checks.
        with self._lock:
            now = time.monotonic()
            expired = [k for k, e in self._entries.items()
                       if e.expires_at <= now]
            for k in expired:
                del self._entries[k]
            return len(self._entries)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self.hits + self.misses
            return {
                "size": len(self._entries),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl_seconds,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": self.hits / total if total else 0.0,
            }
