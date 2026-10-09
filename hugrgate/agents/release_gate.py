"""Agent Nervous System (Campaign XVI) — release gate.

Slice 400.  The campaign's capstone: a single gate that refuses
to ship a broken nervous system.  :class:`NervousSystemReleaseGate`
runs eight checks over an assembled system:

1. ``contracts-valid`` — every registered agent's contract
   validates (376);
2. ``registry-nonempty`` — at least one agent is registered;
3. ``bus-alive`` — a probe signal publishes and delivers;
4. ``triage-functional`` — a probe signal triages without
   raising (377);
5. ``budgets-allocated`` — every registered agent has a
   decision budget (395);
6. ``kill-switch-clear`` — the runaway guard is not tripped
   (394);
7. ``provenance-acyclic`` — the provenance graph is a DAG
   (396);
8. ``replay-deterministic`` — a probe ticket records and
   replays deterministically (397).

:class:`NervousSystem` bundles every campaign component with
:func:`assemble` building a wired default (bus shared across
triage, escalation, review, dispatch, health, cost, breaker,
guard).  :class:`ReleaseReport` carries per-check results,
``passed``, a human ``summary()``, and a wire-safe
:meth:`to_dict` for CI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hugrgate.agents.attention import AttentionPrioritizer
from hugrgate.agents.budgets import BudgetLedger
from hugrgate.agents.bus import EventBus
from hugrgate.agents.contract import validate_contract
from hugrgate.agents.cost import CostRouter
from hugrgate.agents.dispatch import MultiAgentDispatch
from hugrgate.agents.escalation import EscalationPolicy
from hugrgate.agents.health import HealthRouter
from hugrgate.agents.human_review import HumanReviewQueue
from hugrgate.agents.intent import IntentRouter
from hugrgate.agents.loopbreak import LoopBreaker
from hugrgate.agents.memory_read import MemoryReadGate
from hugrgate.agents.memory_write import MemoryWriteGate
from hugrgate.agents.notify import NotificationGate
from hugrgate.agents.privacy import PrivacyRouter
from hugrgate.agents.provenance import AgentProvenanceGraph
from hugrgate.agents.registry import AgentRegistry
from hugrgate.agents.replay import AgentReplay
from hugrgate.agents.runaway import RunawayGuard
from hugrgate.agents.tools import ToolRouter
from hugrgate.agents.triage import EventTriage
from hugrgate.agents.types import AgentSignal, AgentTicket

__all__ = [
    "GateCheck",
    "NervousSystem",
    "NervousSystemReleaseGate",
    "ReleaseReport",
    "assemble",
]


@dataclass(frozen=True)
class GateCheck:
    """One gate check outcome."""

    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class ReleaseReport:
    """The gate's verdict."""

    checks: tuple[GateCheck, ...]
    notes: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        """True when every check passed."""
        return all(c.passed for c in self.checks)

    @property
    def failed(self) -> tuple[GateCheck, ...]:
        """The failing checks."""
        return tuple(c for c in self.checks if not c.passed)

    def summary(self) -> str:
        """Human-readable verdict."""
        lines = [f"nervous-system release gate: "
                 f"{'PASS' if self.passed else 'FAIL'}"]
        for c in self.checks:
            mark = "ok" if c.passed else "FAIL"
            lines.append(f"  [{mark}] {c.name}"
                         + (f": {c.detail}" if c.detail else ""))
        lines.extend(self.notes)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Wire-safe representation."""
        return {
            "passed": self.passed,
            "notes": list(self.notes),
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in self.checks
            ],
        }


@dataclass
class NervousSystem:
    """Every Campaign XVI component, wired together."""

    bus: EventBus = field(default_factory=EventBus)
    registry: AgentRegistry = field(default_factory=AgentRegistry)
    triage: EventTriage = field(default_factory=EventTriage)
    intent_router: IntentRouter = field(default_factory=IntentRouter)
    tool_router: ToolRouter = field(default_factory=ToolRouter)
    memory_write: MemoryWriteGate = field(default_factory=MemoryWriteGate)
    memory_read: MemoryReadGate = field(default_factory=MemoryReadGate)
    notify_gate: NotificationGate = field(default_factory=NotificationGate)
    attention: AttentionPrioritizer = field(
        default_factory=AttentionPrioritizer)
    escalation: EscalationPolicy = field(
        default_factory=EscalationPolicy)
    review_queue: HumanReviewQueue = field(
        default_factory=HumanReviewQueue)
    dispatcher: MultiAgentDispatch = field(
        default_factory=MultiAgentDispatch)
    health: HealthRouter = field(default_factory=HealthRouter)
    cost: CostRouter = field(default_factory=CostRouter)
    privacy: PrivacyRouter = field(default_factory=PrivacyRouter)
    loop_breaker: LoopBreaker = field(default_factory=LoopBreaker)
    runaway: RunawayGuard = field(default_factory=RunawayGuard)
    budgets: BudgetLedger = field(default_factory=BudgetLedger)
    provenance: AgentProvenanceGraph = field(
        default_factory=AgentProvenanceGraph)
    replay: AgentReplay = field(default_factory=AgentReplay)


def assemble() -> NervousSystem:
    """Build a nervous system with the bus shared across components."""
    bus = EventBus()
    return NervousSystem(
        bus=bus,
        triage=EventTriage(bus=bus),
        escalation=EscalationPolicy(bus=bus),
        review_queue=HumanReviewQueue(bus=bus),
        dispatcher=MultiAgentDispatch(bus=bus),
        health=HealthRouter(bus=bus),
        cost=CostRouter(bus=bus),
        notify_gate=NotificationGate(bus=bus),
        loop_breaker=LoopBreaker(bus=bus),
        runaway=RunawayGuard(bus=bus),
    )


class NervousSystemReleaseGate:
    """Release gate over an assembled nervous system."""

    def run(self, system: NervousSystem) -> ReleaseReport:
        """Run all checks; never raises on check failure."""
        checks: list[GateCheck] = [
            self._contracts_valid(system),
            self._registry_nonempty(system),
            self._bus_alive(system),
            self._triage_functional(system),
            self._budgets_allocated(system),
            self._kill_switch_clear(system),
            self._provenance_acyclic(system),
            self._replay_deterministic(system),
        ]
        notes: list[str] = []
        failed = [c for c in checks if not c.passed]
        if failed:
            notes.append(
                f"{len(failed)} check(s) failed: "
                + ", ".join(c.name for c in failed))
        return ReleaseReport(checks=tuple(checks), notes=tuple(notes))

    # -- checks ----------------------------------------------------------
    @staticmethod
    def _contracts_valid(system: NervousSystem) -> GateCheck:
        bad: list[str] = []
        for agent_id in system.registry.agent_ids():
            entry = system.registry.get(agent_id)
            violations = validate_contract(entry.contract)
            if violations:
                bad.append(f"{agent_id}: {violations[0]}")
        return GateCheck(
            name="contracts-valid",
            passed=not bad,
            detail="all contracts valid" if not bad
            else "; ".join(bad),
        )

    @staticmethod
    def _registry_nonempty(system: NervousSystem) -> GateCheck:
        n = len(system.registry)
        return GateCheck(
            name="registry-nonempty",
            passed=n > 0,
            detail=f"{n} agent(s) registered",
        )

    @staticmethod
    def _bus_alive(system: NervousSystem) -> GateCheck:
        seen: list[AgentSignal] = []
        sub = system.bus.subscribe("gate.probe", seen.append)
        try:
            delivery = system.bus.publish(AgentSignal(topic="gate.probe"))
        finally:
            system.bus.unsubscribe(sub)
        ok = delivery.delivered == 1 and len(seen) == 1
        return GateCheck(
            name="bus-alive",
            passed=ok,
            detail="probe delivered" if ok else "probe not delivered",
        )

    @staticmethod
    def _triage_functional(system: NervousSystem) -> GateCheck:
        try:
            decision = system.triage.triage(
                AgentSignal(topic="gate.probe"))
            ok = decision.action == "route"
            detail = f"action={decision.action} queue={decision.queue}"
        except Exception as exc:  # noqa: BLE001 - check must not raise
            ok, detail = False, f"raised: {exc}"
        return GateCheck(name="triage-functional", passed=ok, detail=detail)

    @staticmethod
    def _budgets_allocated(system: NervousSystem) -> GateCheck:
        missing = [
            aid for aid in system.registry.agent_ids()
            if not system.budgets.allocated(aid)
        ]
        return GateCheck(
            name="budgets-allocated",
            passed=not missing,
            detail=(f"{len(system.registry)} agent(s) budgeted")
            if not missing else f"missing budgets: {missing}",
        )

    @staticmethod
    def _kill_switch_clear(system: NervousSystem) -> GateCheck:
        tripped = system.runaway.kill_switch_tripped
        return GateCheck(
            name="kill-switch-clear",
            passed=not tripped,
            detail="tripped" if tripped else "clear",
        )

    @staticmethod
    def _provenance_acyclic(system: NervousSystem) -> GateCheck:
        ok = system.provenance.check_acyclic()
        return GateCheck(
            name="provenance-acyclic",
            passed=ok,
            detail=f"{len(system.provenance)} node(s), acyclic"
            if ok else "cycle detected",
        )

    @staticmethod
    def _replay_deterministic(system: NervousSystem) -> GateCheck:
        ticket = AgentTicket(ticket_id="gate-probe", agent_id="gate",
                             intent="probe")
        system.replay.record_step(
            ticket.ticket_id, "probe", {"in": 1}, {"out": 2})
        try:
            deterministic = system.replay.check_determinism(
                ticket.ticket_id, lambda i, s: {"out": 2})
            report = system.replay.replay(
                ticket.ticket_id, lambda i, s: {"out": 2})
            ok = deterministic and report.fidelity == 1.0
            detail = (f"fidelity={report.fidelity:.2f} "
                      f"deterministic={deterministic}")
        except Exception as exc:  # noqa: BLE001 - check must not raise
            ok, detail = False, f"raised: {exc}"
        finally:
            system.replay.forget(ticket.ticket_id)
        return GateCheck(name="replay-deterministic", passed=ok,
                         detail=detail)
