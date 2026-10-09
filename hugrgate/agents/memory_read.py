"""Agent Nervous System (Campaign XVI) — memory-read gating.

Slice 381.  Reads are the subtler exfiltration path: an agent
with broad clearance but a narrow role must never see raw
episodes above its role's redaction line.  :class:`MemoryReadGate`
enforces the read side of :mod:`hugrgate.memory.access`:

1. **shape** — requested class is on the privacy ladder;
2. **binding** — agent bound with role + clearance (fail closed);
3. **clearance** — agent clearance covers the requested class;
4. **role class** — the role's ``max_class`` covers it
   (``auditor`` never sees ``sensitive`` even with clearance);
5. **redaction** — reads at/above the role's ``redact_at`` line
   return ``redacted=True``: the caller must strip metadata/tags
   before use (the *permit* says redacted; the store view enforces
   it — same contract as :class:`GuardedHistory`);
6. **rate** — per-agent token bucket so a runaway reader cannot
   scrape the store.

Every decision appends to a bounded audit trail
(``agent_id``, class, granted, redacted, purpose, timestamp) for
the provenance graph (396) and human review (385).  Like the write
gate, this gate decides — it never touches the store.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hugrgate.memory.access import ROLE_PERMISSIONS
from hugrgate.privacy import PRIVACY_CLASS_ORDER, class_rank

__all__ = [
    "READ_REASONS",
    "MemoryReadGate",
    "ReadGateConfig",
    "ReadPermit",
]

#: Machine-readable read decision reasons.
READ_REASONS: tuple[str, ...] = (
    "ok",
    "bad_class",
    "unbound_agent",
    "clearance",
    "role_class",
    "rate_limited",
)


@dataclass(frozen=True)
class ReadGateConfig:
    """Gate tuning."""

    max_reads_per_minute: int = 600
    audit_trail_size: int = 1024
    default_role: str = ""  # empty = unbound agents denied (fail closed)


@dataclass(frozen=True)
class ReadPermit:
    """Outcome of a read request."""

    granted: bool
    reason: str
    agent_id: str
    privacy_class: str = ""
    redacted: bool = False


class _Bucket:
    def __init__(self, rate_per_s: float, capacity: int,
                 clock: Callable[[], float]) -> None:
        self._rate = rate_per_s
        self._capacity = capacity
        self._clock = clock
        self._tokens = float(capacity)
        self._last = clock()

    def take(self) -> bool:
        now = self._clock()
        self._tokens = min(
            float(self._capacity),
            self._tokens + (now - self._last) * self._rate,
        )
        self._last = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


class MemoryReadGate:
    """Decides whether an agent may read episodes of a privacy class."""

    def __init__(
        self,
        config: ReadGateConfig | None = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._config = config or ReadGateConfig()
        if self._config.default_role and \
                self._config.default_role not in ROLE_PERMISSIONS:
            raise ValueError(
                f"unknown default_role {self._config.default_role!r}"
            )
        self._clock = clock or time.monotonic
        self._bindings: dict[str, tuple[str, str]] = {}
        self._buckets: dict[str, _Bucket] = {}
        self._audit: deque[dict[str, Any]] = deque(
            maxlen=self._config.audit_trail_size
        )
        self._stats: dict[str, Any] = {
            "requests": 0, "granted": 0, "denied": 0, "redacted": 0,
            "by_reason": {r: 0 for r in READ_REASONS},
        }

    def bind_agent(
        self, agent_id: str, *, role: str, clearance: str
    ) -> None:
        """Bind an agent to a memory role and privacy clearance."""
        if role not in ROLE_PERMISSIONS:
            raise ValueError(f"unknown role {role!r}")
        if clearance not in PRIVACY_CLASS_ORDER:
            raise ValueError(f"unknown clearance {clearance!r}")
        self._bindings[agent_id] = (role, clearance)

    def _bucket(self, agent_id: str) -> _Bucket:
        bucket = self._buckets.get(agent_id)
        if bucket is None:
            bucket = _Bucket(
                rate_per_s=self._config.max_reads_per_minute / 60.0,
                capacity=self._config.max_reads_per_minute,
                clock=self._clock,
            )
            self._buckets[agent_id] = bucket
        return bucket

    def attempt_read(
        self, agent_id: str, privacy_class: str, *, purpose: str = ""
    ) -> ReadPermit:
        """Check a read; on grant the rate quota is consumed."""
        self._stats["requests"] += 1

        def deny(reason: str) -> ReadPermit:
            permit = ReadPermit(granted=False, reason=reason,
                                agent_id=agent_id,
                                privacy_class=privacy_class)
            self._record(permit, purpose)
            return permit

        if privacy_class not in PRIVACY_CLASS_ORDER:
            return deny("bad_class")
        binding = self._bindings.get(agent_id)
        role = binding[0] if binding else self._config.default_role
        clearance = binding[1] if binding else ""
        if not binding and not self._config.default_role:
            return deny("unbound_agent")
        if class_rank(privacy_class) > class_rank(clearance or "public"):
            return deny("clearance")
        perm = ROLE_PERMISSIONS[role]
        if class_rank(privacy_class) > class_rank(perm.max_class):
            return deny("role_class")
        if not self._bucket(agent_id).take():
            return deny("rate_limited")
        redacted = (
            perm.redact_at is not None
            and class_rank(privacy_class) >= class_rank(perm.redact_at)
        )
        permit = ReadPermit(granted=True, reason="ok", agent_id=agent_id,
                            privacy_class=privacy_class, redacted=redacted)
        self._record(permit, purpose)
        return permit

    def _record(self, permit: ReadPermit, purpose: str) -> None:
        if permit.granted:
            self._stats["granted"] += 1
            if permit.redacted:
                self._stats["redacted"] += 1
        else:
            self._stats["denied"] += 1
        self._stats["by_reason"][permit.reason] += 1
        self._audit.append({
            "agent_id": permit.agent_id,
            "privacy_class": permit.privacy_class,
            "granted": permit.granted,
            "redacted": permit.redacted,
            "reason": permit.reason,
            "purpose": purpose[:200],
            "at": self._clock(),
        })

    def audit_trail(self) -> tuple[dict[str, Any], ...]:
        """Bounded read-decision audit trail, oldest first (copies)."""
        return tuple(dict(entry) for entry in self._audit)

    def stats(self) -> dict[str, Any]:
        """Cumulative gate counters (copy)."""
        import copy

        return copy.deepcopy(self._stats)
