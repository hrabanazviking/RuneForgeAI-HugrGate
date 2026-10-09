"""Availability-aware routing. Slice 062.

A rung pointing at a dead backend wastes the climb's latency budget and,
worse, burns the user's time. :class:`AvailabilityTracker` is a
per-backend circuit breaker:

- **closed** (normal): failures are counted; ``failure_threshold``
  consecutive failures *open* the circuit;
- **open**: the backend is skipped without being touched, until
  ``cooldown_s`` elapse;
- **half-open**: one trial request is allowed through; success *closes*
  the circuit, failure re-opens it.

:class:`AvailabilityAwarePlanner` additionally consults
``backend.health()`` at plan time — a backend reporting anything but
``{"status": "ok"}`` is pruned before it can fail. The router feeds
attempt outcomes back through ``LadderRouterV2.note_availability``:
``BackendUnavailable``/``BackendError`` (and unexpected exceptions)
count as failures; a returned result — even one below the confidence
gate — counts as success, because the backend *worked*. Abstentions are
neutral: a backend that politely declines is not a broken backend.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from hugrgate.backend import Backend
from hugrgate.routing.architecture import (RouterContext, RungNode,
                                            RungPlanner, RoutingPlan)

__all__ = [
    "CircuitState",
    "AvailabilityTracker",
    "AvailabilityAwarePlanner",
]


@dataclass
class CircuitState:
    consecutive_failures: int = 0
    open_since: Optional[float] = None  # monotonic seconds, None = closed
    half_open_trial: bool = False


class AvailabilityTracker:
    """Per-backend circuit breaker with health-check integration."""

    def __init__(self, failure_threshold: int = 3,
                 cooldown_s: float = 60.0):
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if cooldown_s < 0:
            raise ValueError("cooldown_s must be non-negative")
        self.failure_threshold = failure_threshold
        self.cooldown_s = cooldown_s
        self._circuits: Dict[str, CircuitState] = {}

    def _circuit(self, name: str) -> CircuitState:
        return self._circuits.setdefault(name, CircuitState())

    def record_success(self, backend_name: str) -> None:
        self._circuits[backend_name] = CircuitState()  # closed, reset

    def record_failure(self, backend_name: str) -> None:
        circuit = self._circuit(backend_name)
        circuit.consecutive_failures += 1
        circuit.half_open_trial = False
        if circuit.consecutive_failures >= self.failure_threshold:
            circuit.open_since = time.monotonic()

    def state(self, backend_name: str) -> str:
        """closed | open | half-open for this backend right now."""
        circuit = self._circuit(backend_name)
        if circuit.open_since is None:
            return "closed"
        if time.monotonic() - circuit.open_since >= self.cooldown_s:
            return "half-open"
        return "open"

    def available(self, backend: Backend,
                  check_health: bool = True) -> Optional[str]:
        """None when the backend may be tried, else the reason."""
        state = self.state(backend.name)
        if state == "open":
            return (f"{backend.name} circuit open "
                    f"({self._circuit(backend.name).consecutive_failures} "
                    f"consecutive failures)")
        if check_health:
            try:
                health = backend.health() or {}
            except Exception as e:  # health check itself failed
                return f"{backend.name} health check raised {type(e).__name__}"
            if health.get("status", "ok") != "ok":
                return (f"{backend.name} unhealthy: "
                        f"status={health.get('status')!r}")
        return None

    def note_trial(self, backend_name: str) -> None:
        """Mark the half-open trial as consumed."""
        self._circuit(backend_name).half_open_trial = True


class AvailabilityAwarePlanner(RungPlanner):
    """Wrap a planner; prune unavailable rungs before they can fail."""

    def __init__(self, inner: RungPlanner, registry,
                 tracker: Optional[AvailabilityTracker] = None,
                 check_health: bool = True):
        self.inner = inner
        self.registry = registry
        self.tracker = tracker or AvailabilityTracker()
        self.check_health = check_health

    def plan(self, ctx: RouterContext) -> RoutingPlan:
        plan = self.inner.plan(ctx)
        kept: List[RungNode] = []
        pruned: List[str] = []
        for node in plan.nodes:
            backend = self.registry.get(node.backend_name)
            reason = (self.tracker.available(backend, self.check_health)
                      if backend is not None else None)
            node.params["availability"] = (
                "unavailable" if reason else self.tracker.state(
                    node.backend_name))
            if reason is None:
                kept.append(node)
            else:
                pruned.append(reason)
        plan.nodes = kept
        plan.created_by = f"{plan.created_by}+availability"
        plan.rationale.append(
            f"availability: pruned {len(pruned)}"
            + (": " + "; ".join(pruned) if pruned else ""))
        return plan
