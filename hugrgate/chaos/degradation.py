"""Degradation plans: ordered playbooks for failure modes (slice 270).

When a fault strikes, the system should degrade according to a plan,
not improvise. A :class:`DegradationPlan` names a failure mode (via
the taxonomy ``code``\ s it answers, e.g. ``"backend_unavailable"``)
and lists the steps to take in order — fail over, serve stale, shed
load, abstain — each step a callable taking a context dict and
returning a human-readable note.

Execution is best-effort: a failing step is recorded and the plan
continues with the next step, because a degradation plan that aborts
halfway is worse than none. The last-resort step of every builtin
plan is an explicit, reasoned abstention — never a silent wrong
answer.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import SpecError

__all__ = [
    "DegradationPlan",
    "DegradationPlanRegistry",
    "DegradationReport",
    "DegradationStep",
    "builtin_degradation_plans",
]

#: A step action: context in, human-readable note out. May raise —
#: the failure is recorded and the plan continues.
StepAction = Callable[[dict[str, Any]], str]

APPLIED = "applied"
FAILED = "failed"
SKIPPED = "skipped"


@dataclass(frozen=True)
class DegradationStep:
    """One step of a degradation plan."""

    name: str
    description: str
    run: StepAction

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise SpecError("degradation step name must be non-empty")
        if not callable(self.run):
            raise SpecError(
                f"degradation step {self.name!r} run must be callable")


@dataclass(frozen=True)
class DegradationPlan:
    """An ordered playbook answering a set of failure codes."""

    name: str
    description: str
    triggers: tuple[str, ...]
    steps: tuple[DegradationStep, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise SpecError("degradation plan name must be non-empty")
        if not self.triggers:
            raise SpecError(
                f"degradation plan {self.name!r} must list at least one "
                f"trigger failure code")
        if not self.steps:
            raise SpecError(
                f"degradation plan {self.name!r} must have at least one "
                f"step")
        names = [s.name for s in self.steps]
        if len(set(names)) != len(names):
            raise SpecError(
                f"degradation plan {self.name!r} has duplicate step names")

    def answers(self, failure_code: str) -> bool:
        return failure_code in self.triggers


@dataclass
class _StepOutcome:
    name: str
    status: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "note": self.note}


@dataclass
class DegradationReport:
    """What a plan execution did, step by step."""

    plan_name: str
    failure_code: str
    steps: list[_StepOutcome]
    started_at: float
    finished_at: float

    @property
    def outcome(self) -> str:
        statuses = {s.status for s in self.steps}
        if statuses == {APPLIED}:
            return "full"
        if APPLIED in statuses:
            return "partial"
        return "none"

    @property
    def degraded_gracefully(self) -> bool:
        """At least one step applied — the plan did *something*."""
        return any(s.status == APPLIED for s in self.steps)

    def to_dict(self) -> dict[str, Any]:
        report = {"plan_name": self.plan_name,
                  "failure_code": self.failure_code,
                  "outcome": self.outcome,
                  "degraded_gracefully": self.degraded_gracefully,
                  "steps": [s.to_dict() for s in self.steps],
                  "started_at": self.started_at,
                  "finished_at": self.finished_at,
                  "duration_s": self.finished_at - self.started_at}
        json.dumps(report)  # contract: always serializable
        return report


class DegradationPlanRegistry:
    """Named degradation plans with trigger matching and execution."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._plans: dict[str, DegradationPlan] = {}

    def register(self, plan: DegradationPlan) -> DegradationPlanRegistry:
        if not isinstance(plan, DegradationPlan):
            raise SpecError(
                "can only register DegradationPlan, got "
                f"{type(plan).__name__}")
        with self._lock:
            if plan.name in self._plans:
                raise SpecError(
                    f"duplicate degradation plan {plan.name!r}")
            self._plans[plan.name] = plan
        return self

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._plans)

    def get(self, name: str) -> DegradationPlan:
        with self._lock:
            try:
                return self._plans[name]
            except KeyError:
                raise SpecError(
                    f"unknown degradation plan {name!r}") from None

    def plans_for(self, failure_code: str) -> list[DegradationPlan]:
        """Plans answering ``failure_code``, in registration order."""
        with self._lock:
            return [p for p in self._plans.values()
                    if p.answers(failure_code)]

    def execute(self, name: str,
                context: Mapping[str, Any] | None = None,
                failure_code: str = "") -> DegradationReport:
        """Run the plan's steps in order; never aborts mid-plan.

        A raising step is recorded as failed and the plan continues.
        A step may also return a note starting with ``"SKIP: "`` to
        mark itself skipped (precondition not met).
        """
        plan = self.get(name)
        ctx = dict(context or {})
        started = time.monotonic()
        outcomes: list[_StepOutcome] = []
        for step in plan.steps:
            try:
                note = step.run(ctx)
            except Exception as e:  # noqa: BLE001 - recorded per step
                outcomes.append(_StepOutcome(
                    step.name, FAILED,
                    f"{type(e).__name__}: {e}"))
                continue
            if note.startswith("SKIP: "):
                outcomes.append(_StepOutcome(
                    step.name, SKIPPED, note[len("SKIP: "):]))
            else:
                outcomes.append(_StepOutcome(step.name, APPLIED, note))
        return DegradationReport(
            plan_name=plan.name, failure_code=failure_code,
            steps=outcomes, started_at=started,
            finished_at=time.monotonic())


def _abstain_step(reason_code: str) -> DegradationStep:
    return DegradationStep(
        name="abstain-with-reason",
        description="Last resort: abstain explicitly rather than answer "
                    "wrong.",
        run=lambda ctx: (
            f"abstaining: no healthy backend and no usable fallback "
            f"(failure={reason_code})"),
    )


def builtin_degradation_plans() -> DegradationPlanRegistry:
    """The shipped playbooks.

    Each step reads its collaborators from the execution context:

    - ``serve-stale-cache`` needs ``cache_lookup``: a zero-arg
      callable returning a cached :class:`DecisionResult` (or None),
      and ``failure_code`` for the abstention note.
    - ``failover-then-abstain`` needs ``failover``: a zero-arg
      callable returning the failover :class:`DecisionResult`.
    """
    registry = DegradationPlanRegistry()

    def probe_cache(ctx: dict[str, Any]) -> str:
        lookup = ctx.get("cache_lookup")
        if lookup is None:
            return "SKIP: no cache_lookup in context"
        cached = lookup()
        if cached is None:
            raise KeyError("stale cache miss")
        return (f"serving stale cached decision "
                f"(value={cached.value!r}, backend={cached.backend!r})")

    registry.register(DegradationPlan(
        name="serve-stale-cache",
        description="On backend failure, serve the last cached decision; "
                    "abstain when the cache has nothing.",
        triggers=("backend_unavailable", "backend_error", "timeout",
                  "retry_budget_exhausted"),
        steps=(DegradationStep(
            name="probe-stale-cache",
            description="Return the cached decision when available.",
            run=probe_cache,
        ), _abstain_step("backend_unavailable")),
    ))

    def attempt_failover(ctx: dict[str, Any]) -> str:
        failover = ctx.get("failover")
        if failover is None:
            return "SKIP: no failover in context"
        result = failover()
        return (f"failed over (value={result.value!r}, "
                f"backend={result.backend!r})")

    registry.register(DegradationPlan(
        name="failover-then-abstain",
        description="On backend failure, try the standby chain; abstain "
                    "when it also fails.",
        triggers=("backend_unavailable", "bulkhead_rejected"),
        steps=(DegradationStep(
            name="failover-to-standby",
            description="Evaluate through the standby backend chain.",
            run=attempt_failover,
        ), _abstain_step("backend_unavailable")),
    ))
    return registry
