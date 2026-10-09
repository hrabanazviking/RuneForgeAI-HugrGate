"""Zero-copy result sharing. Slice 280.

The hot-path inventory's first actionable finding: :class:`DecisionCache`
pays ``copy.deepcopy`` on every ``put`` *and* every cache hit, even
though a cached decision result is never legitimately mutated after it
is stored.  This module removes that tax for immutable results:

- :func:`freeze` — deep-copies a :class:`DecisionResult` once and
  returns a :class:`FrozenDecisionResult` whose attributes *and* nested
  mappings (``distribution``, ``metadata``) reject mutation.  The
  one-time copy at freeze is the *only* copy; everything downstream
  shares.
- :class:`ZeroCopyCache` — a TTL/LRU cache like :class:`DecisionCache`
  that serves the *identical* frozen object on every hit: zero copies
  per hit, zero copies per put (beyond the freeze itself).
- :class:`SharedPayload` — an immutable, pre-encoded ``bytes`` payload
  (e.g. a JSON-encoded result for cluster transport): encoded once,
  served by reference forever.  ``bytes`` are already immutable; the
  class exists to make the "encode once" contract explicit and
  measurable.

Safety rails (not removed, relocated):

- ``DecisionCache`` keeps its deepcopy behavior for *mutable* results —
  the safety rail stays where callers can still mutate.
- :class:`ZeroCopyCache.put` refuses unfrozen results unless
  ``freeze_on_put=True``; a frozen result that somehow mutates raises
  :class:`ZeroCopyError` at the mutation site, not silently downstream.
- Privacy: the same ``PrivacyGuard.cache_allowed`` gate as
  ``DecisionCache`` — zero-copy never caches what must not be retained.

:func:`copy_cost_estimate` measures the deepcopy tax of a result so the
win is a measured number, not a claim.
"""

from __future__ import annotations

import copy
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from hugrgate.errors import ZeroCopyError
from hugrgate.log import get_logger
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import PrivacyGuard
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

logger = get_logger(__name__)

__all__ = [
    "FrozenDecisionResult",
    "SharedPayload",
    "ZeroCopyCache",
    "copy_cost_estimate",
    "freeze",
]


class FrozenDecisionResult:
    """Immutable, shareable snapshot of a :class:`DecisionResult`.

    Attribute writes raise :class:`ZeroCopyError`; ``distribution`` and
    ``metadata`` are exposed as read-only mapping proxies.  Instances
    are safe to share across threads and cache hits without copying.
    """

    __slots__ = (
        "_accepted",
        "_backend",
        "_calibration_profile",
        "_distribution",
        "_fallback_used",
        "_latency_ms",
        "_metadata",
        "_model",
        "_probability",
        "_uncertainty",
        "_value",
    )

    # Slot type declarations (mypy cannot infer them from
    # object.__setattr__ calls in __init__).
    _value: Any
    _probability: float
    _distribution: MappingProxyType
    _uncertainty: float
    _accepted: bool
    _backend: str
    _model: str
    _latency_ms: float
    _calibration_profile: str
    _fallback_used: bool
    _metadata: MappingProxyType

    def __init__(self, result: DecisionResult) -> None:
        # The single permitted deep copy: after this, no copies ever.
        snap = copy.deepcopy(result)
        object.__setattr__(self, "_value", snap.value)
        object.__setattr__(self, "_probability", snap.probability)
        object.__setattr__(self, "_distribution",
                           MappingProxyType(dict(snap.distribution)))
        object.__setattr__(self, "_uncertainty", snap.uncertainty)
        object.__setattr__(self, "_accepted", snap.accepted)
        object.__setattr__(self, "_backend", snap.backend)
        object.__setattr__(self, "_model", snap.model)
        object.__setattr__(self, "_latency_ms", snap.latency_ms)
        object.__setattr__(self, "_calibration_profile",
                           snap.calibration_profile)
        object.__setattr__(self, "_fallback_used", snap.fallback_used)
        object.__setattr__(self, "_metadata",
                           MappingProxyType(dict(snap.metadata)))

    def __setattr__(self, name: str, value: Any) -> None:
        raise ZeroCopyError(
            f"FrozenDecisionResult is immutable; cannot set {name!r}")

    def __delattr__(self, name: str) -> None:
        raise ZeroCopyError(
            f"FrozenDecisionResult is immutable; cannot delete {name!r}")

    # Read-only attribute surface mirroring DecisionResult.
    @property
    def value(self) -> Any: return self._value
    @property
    def probability(self) -> float: return self._probability
    @property
    def distribution(self) -> Mapping[str, float]: return self._distribution
    @property
    def uncertainty(self) -> float: return self._uncertainty
    @property
    def accepted(self) -> bool: return self._accepted
    @property
    def backend(self) -> str: return self._backend
    @property
    def model(self) -> str: return self._model
    @property
    def latency_ms(self) -> float: return self._latency_ms
    @property
    def calibration_profile(self) -> str: return self._calibration_profile
    @property
    def fallback_used(self) -> bool: return self._fallback_used
    @property
    def metadata(self) -> Mapping[str, Any]: return self._metadata

    def thaw(self) -> DecisionResult:
        """Return a mutable :class:`DecisionResult` copy of this snapshot."""
        return DecisionResult(
            value=copy.deepcopy(self._value),
            probability=self._probability,
            distribution=dict(self._distribution),
            uncertainty=self._uncertainty,
            accepted=self._accepted,
            backend=self._backend,
            model=self._model,
            latency_ms=self._latency_ms,
            calibration_profile=self._calibration_profile,
            fallback_used=self._fallback_used,
            metadata=dict(self._metadata),
        )

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, FrozenDecisionResult):
            return (self.value == other.value
                    and self.probability == other.probability
                    and dict(self.distribution) == dict(other.distribution)
                    and self.backend == other.backend)
        if isinstance(other, DecisionResult):
            return self == freeze(other)
        return NotImplemented

    def __repr__(self) -> str:
        return (f"FrozenDecisionResult(value={self._value!r}, "
                f"probability={self._probability!r}, "
                f"backend={self._backend!r})")


def freeze(result: DecisionResult) -> FrozenDecisionResult:
    """Freeze a result into its immutable shareable form."""
    if isinstance(result, FrozenDecisionResult):
        return result
    if not isinstance(result, DecisionResult):
        raise ZeroCopyError(
            f"freeze() needs a DecisionResult, got {type(result).__name__}")
    return FrozenDecisionResult(result)


def copy_cost_estimate(result: DecisionResult,
                       repeats: int = 200) -> dict[str, float]:
    """Measure the deepcopy tax of ``result`` in microseconds per copy.

    Returns ``{"us_per_copy": ..., "repeats": ...}`` — the number the
    zero-copy path eliminates per cache hit.
    """
    if repeats < 1:
        raise ZeroCopyError(
            f"copy_cost_estimate needs repeats >= 1, got {repeats}")
    start = time.perf_counter()
    for _ in range(repeats):
        copy.deepcopy(result)
    elapsed_us = (time.perf_counter() - start) * 1e6
    return {"us_per_copy": elapsed_us / repeats, "repeats": float(repeats)}


class SharedPayload:
    """An immutable pre-encoded bytes payload, served by reference.

    Encode once (e.g. a result's wire form for cluster transport); every
    consumer receives the *same* ``bytes`` object — no re-encoding, no
    copies.  ``bytes`` are immutable, so sharing is inherently safe.
    """

    __slots__ = ("_content_type", "_data")

    def __init__(self, data: bytes, content_type: str = "application/json"
                 ) -> None:
        if not isinstance(data, bytes):
            raise ZeroCopyError(
                f"SharedPayload needs bytes, got {type(data).__name__}")
        self._data = data
        self._content_type = content_type

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> SharedPayload:
        """Encode ``payload`` to JSON once and share the bytes."""
        return cls(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

    @property
    def data(self) -> bytes:
        return self._data

    @property
    def content_type(self) -> str:
        return self._content_type

    def __len__(self) -> int:
        return len(self._data)

    def __bytes__(self) -> bytes:
        return self._data


class ZeroCopyCache:
    """TTL/LRU cache serving shared frozen results — zero copies per hit.

    Mirrors the :class:`DecisionCache` contract (privacy gate, TTL, LRU,
    backend invalidation, hit/miss stats) but stores
    :class:`FrozenDecisionResult` and returns the identical object on
    every hit.  ``put`` requires a frozen result unless
    ``freeze_on_put=True``.
    """

    def __init__(self, ttl_seconds: float = 300.0, max_size: int = 1024,
                 freeze_on_put: bool = False) -> None:
        if ttl_seconds <= 0:
            raise ZeroCopyError(
                f"ttl_seconds must be > 0, got {ttl_seconds!r}")
        if not isinstance(max_size, int) or max_size < 1:
            raise ZeroCopyError(f"max_size must be >= 1, got {max_size!r}")
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self.freeze_on_put = freeze_on_put
        # key -> [frozen_result, expires_at, backend]
        self._entries: OrderedDict[str, list] = OrderedDict()
        self.hits = 0
        self.misses = 0
        self._lock = threading.RLock()

    def _key(self, state: Mapping[str, Any], spec: DecisionSpec,
             policy: DecisionPolicy) -> str:
        from hugrgate.cache import cache_key
        return cache_key(state, spec, policy)

    def get(self, state: Mapping[str, Any], spec: DecisionSpec,
            policy: DecisionPolicy) -> FrozenDecisionResult | None:
        """Return the shared frozen result, or None on miss/expiry/privacy."""
        with self._lock:
            if not PrivacyGuard.cache_allowed(policy):
                return None
            key = self._key(state, spec, policy)
            entry = self._entries.get(key)
            if entry is None:
                self.misses += 1
                return None
            frozen, expires_at, _backend = entry
            if expires_at <= time.monotonic():
                del self._entries[key]
                self.misses += 1
                return None
            self._entries.move_to_end(key)
            self.hits += 1
            return frozen  # the identical object — zero copies

    def put(self, state: Mapping[str, Any], spec: DecisionSpec,
            policy: DecisionPolicy,
            result: DecisionResult | FrozenDecisionResult) -> bool:
        """Store ``result``.  Returns False when privacy forbids caching."""
        with self._lock:
            if not PrivacyGuard.cache_allowed(policy):
                return False
            if isinstance(result, FrozenDecisionResult):
                frozen = result
            elif self.freeze_on_put and isinstance(result, DecisionResult):
                frozen = freeze(result)
            else:
                raise ZeroCopyError(
                    "ZeroCopyCache.put requires a FrozenDecisionResult "
                    "(or freeze_on_put=True)")
            key = self._key(state, spec, policy)
            self._entries[key] = [frozen, time.monotonic() + self.ttl_seconds,
                                  frozen.backend]
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_size:
                self._entries.popitem(last=False)
            return True

    def invalidate_backend(self, backend_name: str) -> int:
        with self._lock:
            doomed = [k for k, e in self._entries.items()
                      if e[2] == backend_name]
            for k in doomed:
                del self._entries[k]
            return len(doomed)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

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
                "copies_per_hit": 0,
            }
