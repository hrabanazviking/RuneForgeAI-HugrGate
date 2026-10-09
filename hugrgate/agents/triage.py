"""Agent Nervous System (Campaign XVI) — event triage API.

Slice 377.  The bus delivers *everything*; the nervous system must
not react to everything.  :class:`EventTriage` is the first
processing stage after the bus: it classifies each
:class:`AgentSignal` into one of three dispositions —

- ``route`` — hand to a named queue for downstream consumers
  (intent routing, escalation, notification);
- ``drop`` — noise the system must never react to (heartbeats,
  duplicates that escaped dedup, known-benign chatter);
- ``defer`` — legitimate but non-urgent work parked until the
  attention budget allows it (slice 383 consumes the defer queue).

Rules are evaluated in insertion order; the first matching rule
wins.  The default rule (always last, irremovable) routes to the
``"default"`` queue at the signal's own priority.  A rule may boost
or clamp priority so triage — not the producer — owns urgency.

Every decision is recorded in stats and, when a bus is attached,
published as a ``triage.decision`` signal (metadata only) so
observability tracing sees the classification path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hugrgate.agents.bus import EventBus, matches
from hugrgate.agents.types import PRIORITY_RANK, AgentSignal

__all__ = [
    "ACTIONS",
    "EventTriage",
    "TriageDecision",
    "TriageRule",
]

#: Allowed rule actions.
ACTIONS: tuple[str, ...] = ("route", "drop", "defer")

#: Queues the triage layer knows about.
QUEUES: tuple[str, ...] = ("default", "urgent", "defer", "noise")


@dataclass(frozen=True)
class TriageRule:
    """One classification rule.

    ``topic_pattern`` uses bus pattern syntax (exact, ``"a.*"``,
    ``"*"``).  ``priority_boost`` shifts the signal's priority rank
    (negative clamps it down); the result is clamped to the known
    priority ladder.  ``queue`` is only meaningful for ``route``.
    """

    name: str
    topic_pattern: str
    action: str
    queue: str = "default"
    priority_boost: int = 0
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("rule name must be non-empty")
        if not self.topic_pattern:
            raise ValueError("topic_pattern must be non-empty")
        if self.action not in ACTIONS:
            raise ValueError(f"action must be one of {ACTIONS}")
        if self.queue not in QUEUES:
            raise ValueError(f"queue must be one of {QUEUES}")


@dataclass(frozen=True)
class TriageDecision:
    """The disposition of one signal."""

    signal: AgentSignal
    action: str
    queue: str
    priority: str
    rule_name: str
    reason: str
    dropped: bool = False
    deferred: bool = False


def _shift_priority(priority: str, boost: int) -> str:
    from hugrgate.agents.types import PRIORITIES

    rank = PRIORITY_RANK[priority] + boost
    rank = max(0, min(rank, len(PRIORITIES) - 1))
    return PRIORITIES[rank]


class EventTriage:
    """Ordered-rule event triage sitting in front of the bus consumers."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus = bus
        self._rules: list[TriageRule] = []
        self._stats: dict[str, Any] = {
            "triaged": 0,
            "routed": 0,
            "dropped": 0,
            "deferred": 0,
            "by_queue": {q: 0 for q in QUEUES},
            "by_rule": {},
        }

    # -- rules ---------------------------------------------------------
    def add_rule(self, rule: TriageRule) -> None:
        """Append ``rule``; names must be unique."""
        if any(r.name == rule.name for r in self._rules):
            raise ValueError(f"duplicate triage rule {rule.name!r}")
        self._rules.append(rule)

    def remove_rule(self, name: str) -> bool:
        """Remove the rule called ``name``; True when it existed."""
        for i, rule in enumerate(self._rules):
            if rule.name == name:
                del self._rules[i]
                return True
        return False

    def rules(self) -> tuple[TriageRule, ...]:
        """Current rules in evaluation order."""
        return tuple(self._rules)

    # -- triage --------------------------------------------------------
    def triage(self, signal: AgentSignal) -> TriageDecision:
        """Classify ``signal``; first matching rule wins."""
        rule = next(
            (r for r in self._rules if matches(r.topic_pattern, signal.topic)),
            None,
        )
        if rule is None:
            decision = TriageDecision(
                signal=signal,
                action="route",
                queue="default",
                priority=signal.priority,
                rule_name="default",
                reason="no rule matched; default route",
            )
        else:
            priority = _shift_priority(signal.priority, rule.priority_boost)
            decision = TriageDecision(
                signal=signal,
                action=rule.action,
                queue=rule.queue if rule.action == "route" else "noise",
                priority=priority,
                rule_name=rule.name,
                reason=rule.reason or f"matched rule {rule.name!r}",
                dropped=rule.action == "drop",
                deferred=rule.action == "defer",
            )
        self._record(decision)
        if self._bus is not None:
            self._bus.publish(
                AgentSignal(
                    topic="triage.decision",
                    payload={
                        "in_topic": signal.topic,
                        "action": decision.action,
                        "queue": decision.queue,
                        "rule": decision.rule_name,
                    },
                    priority="low",
                    trace_id=signal.trace_id,
                    source="triage",
                )
            )
        return decision

    def _record(self, decision: TriageDecision) -> None:
        self._stats["triaged"] += 1
        if decision.dropped:
            self._stats["dropped"] += 1
        elif decision.deferred:
            self._stats["deferred"] += 1
        else:
            self._stats["routed"] += 1
        self._stats["by_queue"][decision.queue] += 1
        by_rule = self._stats["by_rule"]
        by_rule[decision.rule_name] = by_rule.get(decision.rule_name, 0) + 1

    def stats(self) -> dict[str, Any]:
        """Cumulative triage counters (deep copy)."""
        import copy

        return copy.deepcopy(self._stats)

    # -- convenience constructors --------------------------------------
    @classmethod
    def with_defaults(cls, bus: EventBus | None = None) -> EventTriage:
        """Triage with the standard noise/urgency rule set.

        - heartbeats and telemetry chatter → drop;
        - escalation / runaway / loop topics → urgent queue, +1 priority;
        - low-priority bulk topics → defer.
        """
        triage = cls(bus=bus)
        triage.add_rule(
            TriageRule(
                name="drop-heartbeats",
                topic_pattern="*.heartbeat",
                action="drop",
                reason="heartbeat noise",
            )
        )
        triage.add_rule(
            TriageRule(
                name="drop-telemetry",
                topic_pattern="telemetry.*",
                action="drop",
                reason="telemetry chatter",
            )
        )
        for topic in ("agent.escalated", "agent.loop", "agent.runaway"):
            triage.add_rule(
                TriageRule(
                    name=f"urgent-{topic}",
                    topic_pattern=topic,
                    action="route",
                    queue="urgent",
                    priority_boost=1,
                    reason="safety-critical agent signal",
                )
            )
        triage.add_rule(
            TriageRule(
                name="defer-bulk",
                topic_pattern="bulk.*",
                action="defer",
                reason="non-urgent bulk work",
            )
        )
        return triage
