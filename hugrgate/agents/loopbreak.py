"""Agent Nervous System (Campaign XVI) — agent loop-breaker.

Slice 393.  Agentic loops are the classic failure: planner asks
worker, worker asks planner, forever, burning budget.  :class:`LoopBreaker`
treats delegation as a *call stack* with strict discipline:

- :meth:`observe(ticket_id, caller, callee)` pushes ``callee``
  onto the ticket's delegation stack (``caller`` must be the
  stack top — delegation is a chain, not a graph);
- :meth:`return_to(ticket_id)` pops the stack when a delegation
  completes — returning to a previous agent is legitimate and
  must not trip the breaker;
- pushing an agent already on the stack is a cycle →
  :class:`AgentLoopDetected` (with the cycle path in details);
- stacks deeper than ``max_depth`` trip the breaker too —
  even acyclic chains must terminate.

Detection publishes ``agent.loop`` on the bus (triage's urgent
rules, slice 377, already route it hot).  The breaker is purely
observational: it never kills anything itself — the runaway
guard (394) and escalation policy (384) decide what happens
next.  Tool calls are leaves, not delegation: route them
through the tool router (379), not the breaker.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from hugrgate.agents.bus import EventBus
from hugrgate.agents.types import AgentSignal
from hugrgate.errors import AgentLoopDetected

__all__ = [
    "LoopBreaker",
    "LoopEvent",
]


@dataclass(frozen=True)
class LoopEvent:
    """A detected loop."""

    ticket_id: str
    cycle: tuple[str, ...]
    depth: int


class LoopBreaker:
    """Call-stack discipline for agent delegation."""

    def __init__(
        self,
        *,
        max_depth: int = 16,
        bus: EventBus | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if max_depth < 2:
            raise ValueError("max_depth must be >= 2")
        self._max_depth = max_depth
        self._bus = bus
        self._stacks: dict[str, list[str]] = {}
        self._stats = {"observations": 0, "returns": 0, "loops": 0}

    def observe(
        self, ticket_id: str, caller: str, callee: str
    ) -> tuple[str, ...]:
        """Record ``caller -> callee`` delegation; returns the stack.

        Raises :class:`AgentLoopDetected` on a cycle or when the
        stack would exceed ``max_depth``.
        """
        if not ticket_id or not caller or not callee:
            raise ValueError("ticket_id, caller, and callee are required")
        stack = self._stacks.setdefault(ticket_id, [])
        if stack and stack[-1] != caller:
            raise ValueError(
                f"delegation chain broken: {caller!r} is not the "
                f"stack top ({stack[-1]!r}) for ticket {ticket_id!r}"
            )
        if not stack:
            stack.append(caller)
        self._stats["observations"] += 1
        if callee in stack:
            cycle = (*stack[stack.index(callee):], callee)
            self._stats["loops"] += 1
            event = LoopEvent(ticket_id=ticket_id, cycle=cycle,
                              depth=len(stack))
            self._emit(event)
            raise AgentLoopDetected(
                f"agent loop on ticket {ticket_id!r}: "
                + " -> ".join(cycle),
                ticket_id=ticket_id,
                cycle=list(cycle),
            )
        if len(stack) >= self._max_depth:
            self._stats["loops"] += 1
            event = LoopEvent(ticket_id=ticket_id,
                              cycle=(*stack, callee),
                              depth=len(stack))
            self._emit(event)
            raise AgentLoopDetected(
                f"delegation depth {len(stack) + 1} exceeds max "
                f"{self._max_depth} on ticket {ticket_id!r}",
                ticket_id=ticket_id,
                cycle=[*stack, callee],
            )
        stack.append(callee)
        return tuple(stack)

    def return_to(self, ticket_id: str) -> str:
        """Pop the delegation stack (a delegation completed).

        Returns the agent returning control.  Raises ``ValueError``
        on an empty/unknown stack.
        """
        stack = self._stacks.get(ticket_id)
        if not stack:
            raise ValueError(f"no delegation stack for {ticket_id!r}")
        self._stats["returns"] += 1
        return stack.pop()

    def path(self, ticket_id: str) -> tuple[str, ...]:
        """Current delegation stack for ``ticket_id``."""
        return tuple(self._stacks.get(ticket_id, ()))

    def reset(self, ticket_id: str) -> bool:
        """Forget a ticket's stack; True when it existed."""
        return self._stacks.pop(ticket_id, None) is not None

    def _emit(self, event: LoopEvent) -> None:
        bus = self._bus
        if bus is not None:
            bus.publish(AgentSignal(
                topic="agent.loop",
                payload={"ticket_id": event.ticket_id,
                         "cycle": list(event.cycle),
                         "depth": event.depth},
                priority="critical",
                source="loopbreaker",
            ))

    def stats(self) -> dict[str, int]:
        """Breaker counters (copy)."""
        return dict(self._stats)

    @property
    def max_depth(self) -> int:
        """The configured depth cap."""
        return self._max_depth
