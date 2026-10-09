"""Retention policies. Slice 239.

Data should not outlive its purpose. :class:`RetentionPolicy`
declares per-privacy-class maximum ages; :func:`purge_expired`
removes overdue records from a :class:`ProvenanceStore` (via the
chain-safe :meth:`ProvenanceStore.purge`), and
:meth:`RetentionPolicy.cache_ttl_for` caps decision-cache TTLs.

Defaults (seconds; ``None`` = unbounded):

- ``public`` — unbounded;
- ``standard`` — 30 days;
- ``sensitive`` — 7 days;
- ``strict`` — 24 hours;
- ``forbidden`` — 0: never persist (purged on the next sweep).

``forbidden`` records are still *created* (the decision happened and
the chain binds it) but must not be *retained* — the next purge
removes them. Operators wanting zero creation should not log at all.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from hugrgate.policy import DecisionPolicy
from hugrgate.provenance import DecisionRecord, ProvenanceStore

__all__ = [
    "RETENTION_DEFAULTS",
    "RetentionPolicy",
    "purge_expired",
]

#: Default maximum age per privacy class, in seconds (None = unbounded).
RETENTION_DEFAULTS: dict[str, float | None] = {
    "public": None,
    "standard": 30 * 24 * 3600,
    "sensitive": 7 * 24 * 3600,
    "strict": 24 * 3600,
    "forbidden": 0,
}


class RetentionPolicy:
    """Per-class retention limits.

    Parameters
    ----------
    max_age_seconds:
        Privacy class -> maximum age in seconds (``None`` = unbounded).
        Unknown classes fall back to the strictest default (24h) —
        fail closed. ``0`` means "do not retain".
    """

    def __init__(self,
                 max_age_seconds: Mapping[str, float | None] | None = None):
        self._max_age: dict[str, float | None] = dict(RETENTION_DEFAULTS)
        for cls, age in (max_age_seconds or {}).items():
            if age is not None and age < 0:
                raise ValueError(
                    f"max age for {cls!r} must be >= 0, got {age}")
            self._max_age[str(cls)] = age

    def max_age_for(self, privacy_class: str) -> float | None:
        """Maximum age in seconds (None = unbounded)."""
        if privacy_class in self._max_age:
            return self._max_age[privacy_class]
        # Unknown class: fail closed to the strict default.
        return RETENTION_DEFAULTS["strict"]

    def is_expired(self, record: DecisionRecord,
                   now: float | None = None) -> bool:
        """True when the record is older than its class allows."""
        now = time.time() if now is None else now
        age_limit = self.max_age_for(
            record.metadata.get("privacy_class", "strict"))
        if age_limit is None:
            return False
        return (now - record.timestamp) > age_limit

    def cache_ttl_for(self, policy: DecisionPolicy,
                      default_ttl: float) -> float:
        """Effective cache TTL: the default capped by the class limit."""
        limit = self.max_age_for(policy.privacy_class)
        if limit is None:
            return default_ttl
        return max(0.0, min(default_ttl, limit))

    def to_dict(self) -> dict[str, Any]:
        return {"max_age_seconds": dict(self._max_age)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RetentionPolicy:
        return cls(max_age_seconds=data.get("max_age_seconds"))


def purge_expired(store: ProvenanceStore,
                  policy: RetentionPolicy | None = None,
                  now: float | None = None,
                  on_purge: Callable[[DecisionRecord], None] | None = None
                  ) -> int:
    """Remove expired records from ``store``; return the count removed.

    ``on_purge`` fires per removed record *before* removal (secure
    deletion hooks, slice 240, attach here).
    """
    policy = policy or RetentionPolicy()
    now = time.time() if now is None else now
    expired = [r for r in store.recent(store.count())
               if policy.is_expired(r, now=now)]
    if on_purge is not None:
        for record in expired:
            on_purge(record)
    hashes = {r.record_hash for r in expired}
    return store.purge(lambda r: r.record_hash in hashes)
