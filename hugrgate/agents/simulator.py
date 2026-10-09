"""Agent Nervous System (Campaign XVI) — agent simulator.

Slice 398.  You cannot chaos-test a nervous system against
production agents.  :class:`AgentSimulator` runs *scripted*
agents through the real nervous-system machinery — bus,
loop-breaker, runaway guard, dispatcher — so failure modes can
be rehearsed deterministically:

- behaviors: ``"honest"`` (delegates and completes),
  ``"slow"`` (honest, high latency), ``"faulty"`` (raises),
  ``"looping"`` (delegates back to its caller — trips the
  loop-breaker), ``"escalating"`` (burns escalation budget —
  trips the runaway guard), or any custom callable;
- a *script* is a list of ``{"ticket", "from", "to",
  "intent"}`` delegation steps; the simulator plays each
  through :class:`LoopBreaker` and dispatches on the
  destination's behavior;
- *faults* are callables ``(sim, step_index)`` invoked before
  each step — the chaos hook (trip the kill switch at step N,
  mute the bus, ...), reusing the chaos-experiment mindset
  without duplicating :mod:`hugrgate.chaos`;
- :class:`SimulationReport` counts successes, failures, loops,
  runaways, and per-agent outcomes.  Seeded RNG: the same
  script + seed replays identically.

The simulator is deterministic and in-process — a rehearsal
stage, not a load generator.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hugrgate.agents.bus import EventBus
from hugrgate.agents.dispatch import MultiAgentDispatch
from hugrgate.agents.loopbreak import LoopBreaker
from hugrgate.agents.runaway import RunawayGuard, RunawayLimits
from hugrgate.agents.types import AgentTicket
from hugrgate.errors import AgentLoopDetected, AgentRunaway

__all__ = [
    "BEHAVIORS",
    "AgentSimulator",
    "SimContext",
    "SimulationReport",
]

#: Built-in behavior names.
BEHAVIORS: tuple[str, ...] = (
    "honest", "slow", "faulty", "looping", "escalating",
)

#: Behavior verdicts.
COMPLETE, FAIL, LOOP, ESCALATE = "complete", "fail", "loop", "escalate"


@dataclass
class SimContext:
    """What a behavior sees at its step."""

    ticket_id: str
    agent_id: str
    caller: str
    intent: str
    step_index: int
    rng: random.Random


#: A behavior maps a context to a verdict.
Behavior = Callable[[SimContext], str]


def _honest(ctx: SimContext) -> str:
    return COMPLETE


def _slow(ctx: SimContext) -> str:
    return COMPLETE


def _faulty(ctx: SimContext) -> str:
    return FAIL


def _looping(ctx: SimContext) -> str:
    return LOOP


def _escalating(ctx: SimContext) -> str:
    return ESCALATE


_BUILTINS: dict[str, Behavior] = {
    "honest": _honest, "slow": _slow, "faulty": _faulty,
    "looping": _looping, "escalating": _escalating,
}


@dataclass(frozen=True)
class SimulationReport:
    """Outcome of a simulated script."""

    steps: int
    successes: int
    failures: int
    loops_detected: int
    runaways: int
    escalations: int
    per_agent: dict[str, dict[str, int]] = field(default_factory=dict)
    seed: int | None = None

    @property
    def success_rate(self) -> float:
        """Fraction of steps completing."""
        return self.successes / self.steps if self.steps else 1.0


class AgentSimulator:
    """Deterministic rehearsal harness for the nervous system."""

    def __init__(
        self,
        *,
        runaway_limits: RunawayLimits | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self._bus = bus or EventBus()
        self._breaker = LoopBreaker(bus=self._bus)
        self._guard = RunawayGuard(limits=runaway_limits, bus=self._bus)
        self._dispatcher = MultiAgentDispatch(bus=self._bus)
        self._behaviors: dict[str, Behavior] = {}

    @property
    def bus(self) -> EventBus:
        """The simulator's event bus (attach observers in tests)."""
        return self._bus

    @property
    def guard(self) -> RunawayGuard:
        """The simulator's runaway guard (faults can trip it)."""
        return self._guard

    def add_agent(
        self, agent_id: str, behavior: str | Behavior
    ) -> None:
        """Register a scripted agent."""
        if isinstance(behavior, str):
            if behavior not in _BUILTINS:
                raise ValueError(
                    f"unknown behavior {behavior!r}; "
                    f"choose from {BEHAVIORS} or pass a callable")
            behavior = _BUILTINS[behavior]
        self._behaviors[agent_id] = behavior

    def run(
        self,
        script: list[dict[str, Any]],
        *,
        seed: int | None = None,
        faults: list[Callable[[AgentSimulator, int], None]] | None = None,
    ) -> SimulationReport:
        """Play ``script`` through the nervous system.

        Each entry: ``{"ticket", "from", "to", "intent"}``.
        ``faults`` run before each step (chaos hooks).
        """
        rng = random.Random(seed)
        counts = {"successes": 0, "failures": 0, "loops": 0,
                  "runaways": 0, "escalations": 0}
        per_agent: dict[str, dict[str, int]] = {}
        faults = faults or []

        def tally(agent_id: str, key: str) -> None:
            per_agent.setdefault(agent_id, {}).setdefault(key, 0)
            per_agent[agent_id][key] += 1

        for i, entry in enumerate(script):
            for fault in faults:
                fault(self, i)
            ticket_id = str(entry["ticket"])
            caller, callee = str(entry["from"]), str(entry["to"])
            intent = str(entry.get("intent", "sim"))
            ticket = AgentTicket(ticket_id=ticket_id, agent_id=callee,
                                 intent=intent)
            behavior = self._behaviors.get(callee, _honest)
            try:
                self._breaker.observe(ticket_id, caller, callee)
            except AgentLoopDetected:
                counts["loops"] += 1
                tally(callee, "loops")
                continue
            ctx = SimContext(ticket_id=ticket_id, agent_id=callee,
                             caller=caller, intent=intent,
                             step_index=i, rng=rng)
            verdict = behavior(ctx)
            if verdict == FAIL:
                counts["failures"] += 1
                tally(callee, "failures")
                self._breaker.return_to(ticket_id)
            elif verdict == LOOP:
                try:
                    self._breaker.observe(ticket_id, callee, caller)
                except AgentLoopDetected:
                    counts["loops"] += 1
                    tally(callee, "loops")
                self._breaker.reset(ticket_id)
            elif verdict == ESCALATE:
                try:
                    self._guard.check_escalation(ticket)
                    counts["escalations"] += 1
                    tally(callee, "escalations")
                except AgentRunaway:
                    counts["runaways"] += 1
                    tally(callee, "runaways")
                self._breaker.return_to(ticket_id)
            else:  # COMPLETE (slow adds latency flavor only)
                counts["successes"] += 1
                tally(callee, "successes")
                self._breaker.return_to(ticket_id)
        return SimulationReport(
            steps=len(script),
            successes=counts["successes"],
            failures=counts["failures"],
            loops_detected=counts["loops"],
            runaways=counts["runaways"],
            escalations=counts["escalations"],
            per_agent=per_agent,
            seed=seed,
        )
