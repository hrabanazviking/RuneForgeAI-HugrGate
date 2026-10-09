"""Agent Nervous System (Campaign XVI) — agent health routing.

Slice 388.  The registry (387) knows who *claims* a capability;
the health router knows who *deserves* the traffic.  Every
dispatch result, tool call, and escalation feeds
:meth:`HealthRouter.report`; the router keeps per-agent EWMA
scores and answers the only question that matters at route time:
*among these candidates, who is healthiest right now?*

- ``score(agent_id)`` — EWMA of success samples (1.0 = ok,
  0.0 = failure); unknown agents start neutral at 0.5 — new
  agents get a chance, known-bad agents don't;
- ``pick(candidates, min_score=...)`` — highest score wins,
  ties break by agent id; nobody above the bar raises
  :class:`AgentNotFound` (a routing failure, not a guess);
- ``degraded(agent_id)`` — score below threshold;
- latency is tracked as a separate EWMA (``avg_latency_ms``) so
  a slow-but-correct agent isn't confused with a failing one;
- edge-triggered ``health.degraded`` bus signals fire when an
  agent *crosses* below threshold — not on every bad report —
  so the notification gate (382) pages once;
- :meth:`sync_registry` pushes health flags into the
  :class:`AgentRegistry`, closing the loop: sick agents drop out
  of ``healthy_only`` lookups automatically.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hugrgate.agents.bus import EventBus
from hugrgate.agents.registry import AgentRegistry
from hugrgate.agents.types import AgentSignal
from hugrgate.errors import AgentNotFound

__all__ = [
    "HealthRouter",
    "HealthScore",
]


@dataclass(frozen=True)
class HealthScore:
    """One agent's health snapshot."""

    agent_id: str
    score: float
    samples: int
    avg_latency_ms: float
    error_rate: float
    degraded: bool


class HealthRouter:
    """EWMA health scoring with threshold-based routing."""

    def __init__(
        self,
        *,
        alpha: float = 0.3,
        degrade_threshold: float = 0.5,
        bus: EventBus | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha must be in (0, 1]")
        if not 0.0 <= degrade_threshold <= 1.0:
            raise ValueError("degrade_threshold must be in [0, 1]")
        self._alpha = alpha
        self._threshold = degrade_threshold
        self._bus = bus
        self._clock = clock or time.monotonic
        self._scores: dict[str, float] = {}
        self._latency: dict[str, float] = {}
        self._errors: dict[str, int] = {}
        self._samples: dict[str, int] = {}
        self._degraded_flag: dict[str, bool] = {}

    def report(
        self, agent_id: str, ok: bool, latency_ms: float = 0.0
    ) -> HealthScore:
        """Fold one outcome into the agent's health."""
        if not agent_id:
            raise ValueError("agent_id must be non-empty")
        latency_ms = max(0.0, latency_ms)
        sample = 1.0 if ok else 0.0
        prev = self._scores.get(agent_id, 0.5)
        score = self._alpha * sample + (1.0 - self._alpha) * prev
        self._scores[agent_id] = score
        prev_lat = self._latency.get(agent_id, latency_ms)
        self._latency[agent_id] = (
            self._alpha * latency_ms + (1.0 - self._alpha) * prev_lat
        )
        self._samples[agent_id] = self._samples.get(agent_id, 0) + 1
        if not ok:
            self._errors[agent_id] = self._errors.get(agent_id, 0) + 1
        degraded = score < self._threshold
        was = self._degraded_flag.get(agent_id, False)
        self._degraded_flag[agent_id] = degraded
        if degraded and not was:
            self._emit_degraded(agent_id, score)
        return self.snapshot(agent_id)

    def _emit_degraded(self, agent_id: str, score: float) -> None:
        bus = self._bus
        if bus is not None:
            bus.publish(AgentSignal(
                topic="health.degraded",
                payload={"agent_id": agent_id,
                         "score": round(score, 3),
                         "threshold": self._threshold},
                priority="high",
                source="health",
            ))

    def score(self, agent_id: str) -> float:
        """Current EWMA score (0.5 neutral for unknown agents)."""
        return self._scores.get(agent_id, 0.5)

    def degraded(
        self, agent_id: str, *, threshold: float | None = None
    ) -> bool:
        """True when the agent's score is below ``threshold``."""
        bar = self._threshold if threshold is None else threshold
        return self.score(agent_id) < bar

    def snapshot(self, agent_id: str) -> HealthScore:
        """Full health snapshot for ``agent_id``."""
        samples = self._samples.get(agent_id, 0)
        errors = self._errors.get(agent_id, 0)
        return HealthScore(
            agent_id=agent_id,
            score=self.score(agent_id),
            samples=samples,
            avg_latency_ms=self._latency.get(agent_id, 0.0),
            error_rate=(errors / samples) if samples else 0.0,
            degraded=self.degraded(agent_id),
        )

    def pick(
        self, candidates: tuple[str, ...] | list[str],
        *, min_score: float = 0.0,
    ) -> str:
        """Healthiest candidate at/above ``min_score``.

        Ties break by agent id (deterministic).  Raises
        :class:`AgentNotFound` when nothing qualifies — the caller
        escalates instead of routing blind.
        """
        if not candidates:
            raise ValueError("candidates must not be empty")
        eligible = [c for c in candidates if self.score(c) >= min_score]
        if not eligible:
            raise AgentNotFound(
                "no candidate meets the health bar",
                candidates=list(candidates),
                min_score=min_score,
            )
        return min(eligible, key=lambda c: (-self.score(c), c))

    def sync_registry(self, registry: AgentRegistry) -> dict[str, bool]:
        """Push degraded flags into the registry's health state.

        Returns ``agent_id -> healthy`` for every agent the router
        has seen.  Unknown-to-router agents are untouched.
        """
        result: dict[str, bool] = {}
        for agent_id in self._scores:
            healthy = not self._degraded_flag.get(agent_id, False)
            try:
                registry.set_health(
                    agent_id, healthy,
                    note=f"health score {self._scores[agent_id]:.3f}",
                )
                result[agent_id] = healthy
            except AgentNotFound:
                continue
        return result

    def stats(self) -> dict[str, Any]:
        """Router counters (copy)."""
        return {
            "agents": len(self._scores),
            "degraded": sum(1 for v in self._degraded_flag.values() if v),
        }
