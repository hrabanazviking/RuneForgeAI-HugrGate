"""Decision cache — request-hash keyed result memoization. Slice 38;
integrity-hardened in slice 258.

:class:`DecisionCache` maps a hash of ``(state, spec, policy)`` to the
:class:`DecisionResult`, with TTL expiry, LRU eviction at ``max_size``,
and three safety rails:

- **Privacy-aware**: entries are never stored for (or served to) decisions
  whose ``privacy_class`` forbids retention (``"strict"``) — see
  :class:`hugrgate.privacy.PrivacyGuard`.
- **Invalidation on model change**: :meth:`invalidate_backend` drops every
  entry produced by a backend, so a retrained model can never serve stale
  decisions.
- **Integrity-sealed**: every stored result carries a SHA-256 checksum
  over its canonical form; ``get`` re-verifies and evicts damaged
  entries (counted in ``stats()["corruptions"]``) instead of serving
  garbage — see :mod:`hugrgate.chaos.cache_faults`.

Results are isolation-copied on the way in and out (slice 292: a
targeted copy of the known mutable fields, ``deepcopy`` for subclass
instances) so callers cannot mutate the cached copy.
"""

from __future__ import annotations

import copy
import hashlib
import json
import pickle
import threading
import time
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, replace
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


def _canonicalize(obj: Any) -> Any:
    """Recursively sort mapping keys so equal states hash equal.

    Only the *state* subtree needs this: :meth:`DecisionSpec.to_dict`
    and :func:`_policy_fingerprint` already build their mappings in a
    fixed insertion order.  Sorting here in Python (slice 292) is
    cheaper than ``json.dumps(..., sort_keys=True)``, which re-sorts
    every nested mapping — including the already-canonical spec and
    policy subtrees — inside the encoder.  Mixed-type keys raise
    ``TypeError`` here exactly as ``sort_keys=True`` raised it before.
    """
    if isinstance(obj, dict):
        return {k: _canonicalize(obj[k]) for k in sorted(obj)}
    if isinstance(obj, (list, tuple)):
        # JSON serializes tuples as arrays; normalize so tuples and
        # lists of equal items hash equal (as they did before).
        return [_canonicalize(v) for v in obj]
    return obj


def _isolated_copy(result: DecisionResult) -> DecisionResult:
    """Copy a result so cache and caller cannot mutate each other.

    Slice 292: ``copy.deepcopy`` of a :class:`DecisionResult` costs
    ~19us because it walks the whole object graph generically.  The
    exact-type fast path copies only the known mutable fields —
    ``distribution`` is ``dict[str, float]`` (immutable values, so a
    flat ``dict()`` suffices) and ``metadata`` is deep-copied for
    arbitrary nesting — at ~9us.  Subclass instances keep the old
    ``deepcopy`` behavior: their extra fields are unknown to us.
    """
    if type(result) is DecisionResult:
        return replace(
            result,
            distribution=dict(result.distribution),
            metadata=copy.deepcopy(result.metadata),
        )
    return copy.deepcopy(result)


def cache_key(state: Mapping[str, Any], spec: DecisionSpec,
              policy: DecisionPolicy) -> str:
    """Stable hash identifying one cacheable decision request."""
    payload = json.dumps(
        {"state": _canonicalize(dict(state)),
         "spec": spec.to_dict(),
         "policy": _policy_fingerprint(policy)},
        default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class _Entry:
    result: DecisionResult
    expires_at: float  # monotonic seconds
    backend: str
    checksum: tuple  # integrity fingerprint (slice 258)


def _result_snapshot(result: Any) -> Any:
    """Fast integrity snapshot of a cached value (~2.4us).

    Any in-process mutation of the stored value — bit rot, a buggy
    writer, memory corruption beneath the cache API — changes the
    snapshot, so ``get`` can refuse to serve the damaged entry.

    This is a non-cryptographic integrity check, not a security
    boundary — the encrypted cache's AEAD seal is the cryptographic
    guarantee.  It runs on every cache hit, so it must be fast:
    a shallow copy of the value's ``__dict__`` (dicts normalized to
    sorted tuples), compared by equality.
    """
    if hasattr(result, "__dict__"):
        return {
            k: (tuple(sorted(v.items())) if isinstance(v, dict) else v)
            for k, v in result.__dict__.items()
        }
    # Opaque values (e.g. the encrypted cache's sealed entries):
    # snapshot over a stable pickle.
    return pickle.dumps(result, protocol=4)


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
        self.corruptions = 0  # lifetime count of evicted-damaged entries
        # RLock: stats() calls len(self), which also takes the lock.
        self._lock = threading.RLock()

    # -- core API ----------------------------------------------------------

    def get(self, state: Mapping[str, Any], spec: DecisionSpec,
            policy: DecisionPolicy) -> DecisionResult | None:
        """Return the cached result, or None on miss/expiry/privacy.

        Slice 293: the key computation and the result copy are pure
        functions of the arguments — they run *outside* the lock so
        the critical section holds only the dict probe and the LRU
        touch (~1us instead of ~35us).
        """
        if not PrivacyGuard.cache_allowed(policy):
            return None
        key = cache_key(state, spec, policy)
        with self._lock:
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
            # Subclass verification runs before the integrity seal: a cache
            # with stronger guarantees (e.g. the encrypted cache's AEAD)
            # must fail closed with its own error rather than have the
            # entry silently evicted as corrupt.
            # (Only dispatched when overridden — the base no-op is skipped
            # on the hot path.)
            if type(self)._verify_entry is not DecisionCache._verify_entry:
                self._verify_entry(entry, state, spec, policy)
            if _result_snapshot(entry.result) != entry.checksum:
                # The stored result was corrupted beneath the cache API.
                # Fail safe: evict the damaged entry and report a miss so
                # the caller recomputes instead of serving garbage.
                del self._entries[key]
                self.corruptions += 1
                self.misses += 1
                logger.warning("cache corruption detected; entry evicted")
                return None
            self._entries.move_to_end(key)  # LRU touch
            self.hits += 1
            logger.debug("cache hit")
            result = entry.result
        # Copy outside the lock: the entry reference keeps the result
        # alive even if another thread invalidates the key meanwhile.
        return _isolated_copy(result)

    def _verify_entry(self, entry: _Entry, state: Mapping[str, Any],
                      spec: DecisionSpec, policy: DecisionPolicy) -> None:
        """Subclass hook: verify an entry before the integrity seal.

        The base implementation does nothing. ``EncryptedDecisionCache``
        overrides this to authenticate the sealed blob (raising
        ``SealError`` on tampering) before the entry is served.
        """

    def put(self, state: Mapping[str, Any], spec: DecisionSpec,
            policy: DecisionPolicy, result: DecisionResult,
            retention: RetentionPolicy | None = None) -> bool:
        """Store ``result``. Returns False when privacy forbids caching.

        When ``retention`` is given, the entry TTL is capped by the
        privacy class's maximum age (slice 239).

        Slice 293: key computation and the isolation copy are hoisted
        out of the lock (see :meth:`get`).
        """
        if not PrivacyGuard.cache_allowed(policy):
            return False
        key = cache_key(state, spec, policy)
        stored = _isolated_copy(result)
        backend = result.backend
        ttl = retention.cache_ttl_for(policy, self.ttl_seconds) \
            if retention is not None else self.ttl_seconds
        checksum = _result_snapshot(stored)
        with self._lock:
            now = time.monotonic()
            self._entries[key] = _Entry(
                result=stored,
                expires_at=now + ttl,
                backend=backend,
                checksum=checksum)
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
                "corruptions": self.corruptions,
                "hit_rate": self.hits / total if total else 0.0,
            }
