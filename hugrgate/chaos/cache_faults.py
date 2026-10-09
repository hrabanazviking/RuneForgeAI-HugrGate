"""Cache corruption simulation. Slice 258.

:class:`CacheCorruptor` simulates memory corruption *beneath* the
:class:`~hugrgate.cache.DecisionCache` API — the bit rot, stray
pointer write, or buggy background thread that mutates a stored
result in place. It reaches into the cache's private entry store
deliberately: the corruption it models happens below the level the
public API can see.

The hardened cache (slice 258) seals every entry with a SHA-256
checksum over its canonical form; :meth:`get` re-verifies the seal
and, on mismatch, evicts the damaged entry, counts it in
``stats()["corruptions"]``, and reports a miss so the caller
recomputes instead of serving garbage.

These are test-only tools: nothing in production code paths tampers
with cache entries.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from hugrgate.cache import DecisionCache, cache_key
from hugrgate.errors import SpecError
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "CacheCorruptor",
]


class CacheCorruptor:
    """Tamper with stored cache entries below the public API."""

    def __init__(self, cache: DecisionCache):
        if not isinstance(cache, DecisionCache):
            raise SpecError(
                "CacheCorruptor needs a DecisionCache, got "
                f"{type(cache).__name__}")
        self._cache = cache

    def tamper(self, state: Mapping[str, Any], spec: DecisionSpec,
               policy: DecisionPolicy,
               mutator: Callable[[DecisionResult], None]) -> bool:
        """Apply ``mutator`` to the stored result in place.

        Returns True when an entry existed and was mutated, False on
        a cache miss (nothing to corrupt). The mutation bypasses the
        deep-copy discipline exactly the way sub-API memory
        corruption would.
        """
        key = cache_key(state, spec, policy)
        # Deliberate private access: the corruption being modeled
        # happens below the public API.
        entry = self._cache._entries.get(key)
        if entry is None:
            return False
        mutator(entry.result)
        return True

    def corrupt_value(self, state: Mapping[str, Any], spec: DecisionSpec,
                      policy: DecisionPolicy, value: Any = "CORRUPT") -> bool:
        """Replace the stored result's value with garbage."""
        return self.tamper(state, spec, policy,
                           lambda result: setattr(result, "value", value))

    def corrupt_metadata(self, state: Mapping[str, Any],
                         spec: DecisionSpec, policy: DecisionPolicy,
                         key: str = "chaos", value: Any = "tampered") -> bool:
        """Scribble into the stored result's metadata dict."""
        def scribble(result: DecisionResult) -> None:
            result.metadata[key] = value
        return self.tamper(state, spec, policy, scribble)
