"""Agent Nervous System (Campaign XVI) — memory-write gating.

Slice 380.  Agents that can write to decision memory unchecked can
poison every downstream consumer (retrieval, assisted routing,
compaction).  :class:`MemoryWriteGate` stands between agents and
the memory store, enforcing four checks in order:

1. **shape** — the episode declares a privacy class on the
   :mod:`hugrgate.privacy` ladder;
2. **clearance** — the agent's clearance (from its slice-376
   contract) covers the episode's class (fail closed: unbound
   agents are denied);
3. **role** — the agent's bound role grants writes per
   :data:`hugrgate.memory.access.ROLE_PERMISSIONS` (analysts and
   auditors cannot write, ever);
4. **rate + size + dedup** — per-agent token-bucket rate limit,
   payload size cap, and dedup-key suppression so a looping agent
   cannot flood the store with identical episodes.

A grant is an explicit :class:`WritePermit`; the caller performs
the store write itself (the gate never touches the store — it only
decides).  Denials carry machine-readable ``reason`` codes for the
provenance graph (slice 396).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from hugrgate.memory.access import ROLE_PERMISSIONS
from hugrgate.privacy import PRIVACY_CLASS_ORDER, class_rank

__all__ = [
    "REASONS",
    "MemoryWriteGate",
    "WriteGateConfig",
    "WritePermit",
]

#: Machine-readable denial reasons.
REASONS: tuple[str, ...] = (
    "ok",
    "bad_class",
    "unbound_agent",
    "clearance",
    "role_readonly",
    "rate_limited",
    "too_large",
    "duplicate",
)


@dataclass(frozen=True)
class WriteGateConfig:
    """Gate tuning."""

    max_writes_per_minute: int = 60
    max_payload_bytes: int = 1_048_576
    dedup_window_s: float = 300.0
    default_role: str = ""  # empty = unbound agents denied (fail closed)


@dataclass(frozen=True)
class WritePermit:
    """Outcome of a write request."""

    granted: bool
    reason: str
    agent_id: str
    privacy_class: str = ""


class _Bucket:
    """Tiny token bucket (monotonic clock)."""

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


class MemoryWriteGate:
    """Decides whether an agent may write one episode to memory."""

    def __init__(
        self,
        config: WriteGateConfig | None = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._config = config or WriteGateConfig()
        if self._config.default_role and \
                self._config.default_role not in ROLE_PERMISSIONS:
            raise ValueError(
                f"unknown default_role {self._config.default_role!r}"
            )
        self._clock = clock or time.monotonic
        self._bindings: dict[str, tuple[str, str]] = {}  # agent -> (role, clearance)
        self._buckets: dict[str, _Bucket] = {}
        self._dedup: dict[str, float] = {}
        self._stats: dict[str, Any] = {
            "requests": 0, "granted": 0, "denied": 0,
            "by_reason": {r: 0 for r in REASONS},
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

    def unbind_agent(self, agent_id: str) -> bool:
        """Remove an agent's binding; True when it existed."""
        return self._bindings.pop(agent_id, None) is not None

    def _bucket(self, agent_id: str) -> _Bucket:
        bucket = self._buckets.get(agent_id)
        if bucket is None:
            bucket = _Bucket(
                rate_per_s=self._config.max_writes_per_minute / 60.0,
                capacity=self._config.max_writes_per_minute,
                clock=self._clock,
            )
            self._buckets[agent_id] = bucket
        return bucket

    def attempt_write(
        self, agent_id: str, episode: Mapping[str, object]
    ) -> WritePermit:
        """Check a write; on grant the quota/dedup state is consumed."""
        self._stats["requests"] += 1
        now = self._clock()

        def deny(reason: str, cls: str = "") -> WritePermit:
            self._stats["denied"] += 1
            self._stats["by_reason"][reason] += 1
            return WritePermit(granted=False, reason=reason,
                               agent_id=agent_id, privacy_class=cls)

        cls = episode.get("privacy_class")
        if not isinstance(cls, str) or cls not in PRIVACY_CLASS_ORDER:
            return deny("bad_class", str(cls))
        binding = self._bindings.get(agent_id)
        role = binding[0] if binding else self._config.default_role
        clearance = binding[1] if binding else ""
        if not binding and not self._config.default_role:
            return deny("unbound_agent", cls)
        if class_rank(cls) > class_rank(clearance or "public"):
            return deny("clearance", cls)
        if not ROLE_PERMISSIONS[role].write:
            return deny("role_readonly", cls)
        size = episode.get("size_bytes", 0)
        if not isinstance(size, int) or size < 0:
            size = 0
        if size > self._config.max_payload_bytes:
            return deny("too_large", cls)
        dedup_key = episode.get("dedup_key")
        if isinstance(dedup_key, str) and dedup_key:
            seen = self._dedup.get(dedup_key)
            if seen is not None and \
                    now - seen < self._config.dedup_window_s:
                return deny("duplicate", cls)
        if not self._bucket(agent_id).take():
            return deny("rate_limited", cls)
        if isinstance(dedup_key, str) and dedup_key:
            self._dedup[dedup_key] = now
        self._stats["granted"] += 1
        self._stats["by_reason"]["ok"] += 1
        return WritePermit(granted=True, reason="ok", agent_id=agent_id,
                           privacy_class=cls)

    def stats(self) -> dict[str, object]:
        """Cumulative gate counters (copy)."""
        import copy

        return copy.deepcopy(self._stats)
