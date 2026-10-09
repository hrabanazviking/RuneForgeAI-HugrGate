"""Memory retention controls. Slice 316.

The Campaign XII worker flagged unbounded ``ProvenanceStore`` growth
(+1.3 GB RSS over 1M decisions). Memory must not repeat that mistake:
this module bounds the episode store three ways.

- **TTL per privacy class** — reuses
  :data:`hugrgate.privacy_retention.RETENTION_DEFAULTS` (``forbidden``
  = 0: purged on the next sweep, exactly like provenance retention);
- **episode count quota** — oldest-first eviction;
- **byte quota** — oldest-first eviction against
  :meth:`DecisionHistory.estimate_bytes
  <hugrgate.memory.history.DecisionHistory.estimate_bytes>`.

:func:`enforce_quotas` applies all three and returns a
:class:`RetentionReport`. :func:`check_quota` is the non-mutating
probe (``ok`` / ``warn`` / ``over``). When ``max_bytes`` is smaller
than the smallest retained episode — so nothing could ever be
retained — :func:`enforce_quotas` raises :class:`MemoryQuotaExceeded`
instead of silently enforcing total amnesia.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import MemoryQuotaExceeded
from hugrgate.memory.query import MemoryQuery
from hugrgate.memory.types import HistoryLike
from hugrgate.privacy_retention import RETENTION_DEFAULTS

__all__ = [
    "MemoryQuota",
    "QuotaStatus",
    "RetentionReport",
    "check_quota",
    "enforce_quotas",
]


@dataclass(frozen=True)
class MemoryQuota:
    """Retention bounds. ``None`` = unbounded for that dimension."""

    max_episodes: int | None = None
    max_bytes: int | None = None
    warn_bytes: int | None = None
    ttl_overrides: dict[str, float | None] | None = None

    def __post_init__(self) -> None:
        if self.max_episodes is not None and self.max_episodes < 1:
            raise ValueError("max_episodes must be >= 1")
        if self.max_bytes is not None and self.max_bytes < 1:
            raise ValueError("max_bytes must be >= 1")
        if self.warn_bytes is not None and self.warn_bytes < 1:
            raise ValueError("warn_bytes must be >= 1")
        if (self.max_bytes is not None and self.warn_bytes is not None
                and self.warn_bytes > self.max_bytes):
            raise ValueError("warn_bytes must be <= max_bytes")

    def max_age_for(self, privacy_class: str) -> float | None:
        """TTL in seconds for a privacy class (None = keep forever)."""
        if self.ttl_overrides and privacy_class in self.ttl_overrides:
            return self.ttl_overrides[privacy_class]
        return RETENTION_DEFAULTS.get(privacy_class)


@dataclass(frozen=True)
class QuotaStatus:
    """Non-mutating quota probe."""

    status: str  # "ok" | "warn" | "over"
    episodes: int
    bytes: int
    quota: MemoryQuota

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "episodes": self.episodes,
            "bytes": self.bytes,
        }


@dataclass
class RetentionReport:
    """What :func:`enforce_quotas` did."""

    ttl_purged: int = 0
    count_evicted: int = 0
    bytes_evicted: int = 0
    bytes_before: int = 0
    bytes_after: int = 0
    episodes_before: int = 0
    episodes_after: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ttl_purged": self.ttl_purged,
            "count_evicted": self.count_evicted,
            "bytes_evicted": self.bytes_evicted,
            "bytes_before": self.bytes_before,
            "bytes_after": self.bytes_after,
            "episodes_before": self.episodes_before,
            "episodes_after": self.episodes_after,
        }


def check_quota(history: HistoryLike, quota: MemoryQuota) -> QuotaStatus:
    """Probe quota state without mutating anything."""
    episodes = history.count()
    n_bytes = history.estimate_bytes()
    over = ((quota.max_episodes is not None and episodes > quota.max_episodes)
            or (quota.max_bytes is not None and n_bytes > quota.max_bytes))
    warn = (not over and quota.warn_bytes is not None
            and n_bytes > quota.warn_bytes)
    return QuotaStatus(status="over" if over else "warn" if warn else "ok",
                       episodes=episodes, bytes=n_bytes, quota=quota)


def enforce_quotas(history: HistoryLike, quota: MemoryQuota, *,
                   now: float | None = None) -> RetentionReport:
    """Enforce TTL, count, and byte quotas; return what happened.

    Order: TTL purges first (expired data has no business occupying
    quota), then oldest-first eviction for count, then for bytes.
    Raises :class:`MemoryQuotaExceeded` when the byte quota cannot be
    satisfied even by an empty history.
    """
    current = time.time() if now is None else now
    report = RetentionReport(
        bytes_before=history.estimate_bytes(),
        episodes_before=history.count(),
    )

    # 1. TTL per privacy class (None = keep forever).
    def expired(episode) -> bool:
        max_age = quota.max_age_for(episode.privacy_class)
        return max_age is not None and \
            current - episode.recorded_at > max_age

    report.ttl_purged = history.purge(expired)

    # 2. Count quota, oldest first.
    if quota.max_episodes is not None:
        over = history.count() - quota.max_episodes
        if over > 0:
            oldest = history.find(
                MemoryQuery(sort_by="recorded_at", descending=False,
                            limit=over))
            doomed = {e.episode_id for e in oldest}
            report.count_evicted = history.purge(
                lambda e: e.episode_id in doomed)

    # 3. Byte quota, oldest first.
    if quota.max_bytes is not None:
        if history.count() > 0:
            smallest = min(
                _episode_bytes(e)
                for e in history.find(MemoryQuery()))
            if smallest > quota.max_bytes:
                raise MemoryQuotaExceeded(
                    f"max_bytes={quota.max_bytes} is unsatisfiable: "
                    f"the smallest retained episode needs ~{smallest} "
                    f"bytes; nothing could ever be retained",
                    max_bytes=quota.max_bytes)
        while history.estimate_bytes() > quota.max_bytes \
                and history.count() > 0:
            oldest = history.find(
                MemoryQuery(sort_by="recorded_at", descending=False,
                            limit=1))
            doomed = {oldest[0].episode_id}
            history.purge(
                lambda e, doomed=doomed: e.episode_id in doomed)
            report.bytes_evicted += 1

    report.bytes_after = history.estimate_bytes()
    report.episodes_after = history.count()
    return report


def _episode_bytes(episode) -> int:
    """Byte estimate for one episode (mirrors estimate_bytes)."""
    body = json.dumps(episode.to_dict(), sort_keys=True, default=str)
    return len(body.encode("utf-8")) + 512
