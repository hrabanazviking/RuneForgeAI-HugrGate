"""Ensemble cache — don't re-ask the council. Slice 121.

Member backends can be expensive; repeated identical states should
not re-pay the full vote. :class:`EnsembleCache` is a TTL + LRU
cache keyed on the canonical ``(state, spec, strategy)`` triple:

- **TTL**: entries expire after ``ttl_seconds`` (monotonic clock);
- **LRU**: beyond ``maxsize`` entries the least-recently-used goes;
- **privacy**: ``privacy="strict"`` evaluations bypass the cache
  entirely — sensitive states are never written to it;
- **invalidation**: :meth:`invalidate_member` drops every entry
  whose council included that member (its votes are stale);
- **isolation**: results are deep-copied on the way in and on the
  way out, so no caller can corrupt the cache through a held
  reference (same discipline as :class:`ProvenanceStore`).

:class:`CachedEnsemble` wraps an :class:`Ensemble` with this policy.
Changing fitted models or strategy options changes outputs without
changing the key — use a fresh cache (or :meth:`invalidate`) then.
"""

from __future__ import annotations

import copy
import json
import time
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any

from hugrgate.errors import PolicyError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "CachedEnsemble",
    "EnsembleCache",
]

_PRIVACY_LEVELS = ("standard", "strict")


def _cache_key(state: Mapping[str, Any], spec: DecisionSpec,
               strategy: str) -> str:
    payload = {"state": dict(state), "spec": spec.to_dict(),
               "strategy": strategy}
    return json.dumps(payload, sort_keys=True, default=str)


class EnsembleCache:
    """TTL + LRU cache of ensemble decisions."""

    def __init__(self, maxsize: int = 128,
                 ttl_seconds: float = 300.0):
        if maxsize < 1:
            raise PolicyError(f"maxsize must be >= 1, got {maxsize}")
        if ttl_seconds < 0:
            raise PolicyError(
                f"ttl_seconds must be >= 0, got {ttl_seconds}")
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        # key -> (stored_at, member_names, result)
        self._entries: OrderedDict[str, tuple[float, list[str], DecisionResult]] = \
            OrderedDict()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def _expired(self, stored_at: float) -> bool:
        return (time.monotonic() - stored_at) >= self.ttl_seconds

    def get(self, key: str) -> DecisionResult | None:
        entry = self._entries.get(key)
        if entry is None:
            self.misses += 1
            return None
        stored_at, _, result = entry
        if self._expired(stored_at):
            del self._entries[key]
            self.misses += 1
            return None
        self._entries.move_to_end(key)
        self.hits += 1
        return copy.deepcopy(result)

    def put(self, key: str, result: DecisionResult,
            member_names: list[str]) -> None:
        self._entries[key] = (time.monotonic(), list(member_names),
                              copy.deepcopy(result))
        self._entries.move_to_end(key)
        while len(self._entries) > self.maxsize:
            self._entries.popitem(last=False)
            self.evictions += 1

    def invalidate_member(self, member: str) -> int:
        """Drop entries whose council included ``member``. Returns count."""
        doomed = [k for k, (_, names, _)
                  in self._entries.items() if member in names]
        for k in doomed:
            del self._entries[k]
        return len(doomed)

    def invalidate(self) -> int:
        n = len(self._entries)
        self._entries.clear()
        return n

    def stats(self) -> dict[str, Any]:
        return {"size": len(self._entries),
                "maxsize": self.maxsize,
                "ttl_seconds": self.ttl_seconds,
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions}

    def __len__(self) -> int:
        return len(self._entries)


class CachedEnsemble:
    """An :class:`Ensemble` with a caching policy around ``evaluate``."""

    def __init__(self, ensemble, cache: EnsembleCache | None = None):
        from hugrgate.ensemble.api import Ensemble
        if not isinstance(ensemble, Ensemble):
            raise PolicyError(
                f"CachedEnsemble wraps an Ensemble, got "
                f"{type(ensemble).__name__}")
        self.ensemble = ensemble
        self.cache = cache if cache is not None else EnsembleCache()

    @property
    def name(self) -> str:
        return self.ensemble.name

    @property
    def members(self):
        return self.ensemble.members

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None,
                 privacy: str = "standard") -> DecisionResult:
        """Evaluate, caching unless ``privacy="strict"``."""
        if privacy not in _PRIVACY_LEVELS:
            raise PolicyError(
                f"privacy must be one of {list(_PRIVACY_LEVELS)}, "
                f"got {privacy!r}")
        if privacy == "strict":
            return self.ensemble.evaluate(state, spec, context)
        key = _cache_key(state, spec, self.ensemble.strategy)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        result = self.ensemble.evaluate(state, spec, context)
        members = [m.name for m in self.ensemble.members]
        self.cache.put(key, result, members)
        return result

    def invalidate_member(self, member: str) -> int:
        return self.cache.invalidate_member(member)

    def invalidate(self) -> int:
        return self.cache.invalidate()

    def stats(self) -> dict[str, Any]:
        return self.cache.stats()
