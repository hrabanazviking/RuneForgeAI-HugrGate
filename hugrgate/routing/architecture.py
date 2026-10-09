"""Router architecture v2 — plan/execute separation. Slice 051.

The v1 :class:`~hugrgate.ladder.LadderRouter` interleaves *deciding which
rungs to try* with *actually trying them*. Architecture v2 splits the two
concerns:

- a **planner** turns a :class:`RouterContext` into a :class:`RoutingPlan`
  (an ordered list of :class:`RungNode`), and
- an **executor** walks the plan, producing a decision and an audit trail.

This makes routing inspectable (the plan exists before any backend runs),
replayable (slice 070), simulable (slice 071), and explainable (slice 069).
:class:`LadderRouterV2` subclasses the v1 router so every existing
``LadderRouter`` construction site keeps working; the new surface is
additive only.

Slice 051 also refactors :class:`~hugrgate.ladder.LadderRouter` itself
(Anti-Checkbox Rule): the four pre-run pruning checks are extracted into
:meth:`~hugrgate.ladder.LadderRouter.precheck`, which the v2 planner
reuses instead of duplicating the logic.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Protocol, Tuple

from hugrgate.errors import PolicyError, SpecError
from hugrgate.ladder import LadderRouter, LadderRung
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "RungMode",
    "RoutingOptions",
    "RouterContext",
    "RungNode",
    "RoutingPlan",
    "RoutingDecision",
    "RungPlanner",
    "RungExecutor",
    "SerialPlanExecutor",
    "LadderRouterV2",
]


class RungMode(str, Enum):
    """How the rungs of a plan relate to each other at execution time."""

    SERIAL = "serial"      # try in order, stop at first gate clear
    PARALLEL = "parallel"  # speculative fan-out; first gate clear wins
    HEDGED = "hedged"      # primary first, backup launched after a delay


@dataclass
class RoutingOptions:
    """Per-request routing knobs. All fields optional; invalid values fail fast.

    These ride alongside (never inside) :class:`DecisionPolicy`: the policy
    carries application thresholds; the options carry *how* the router
    should spend the ladder to meet them.
    """

    qos: str = "standard"               # best_effort|standard|priority|critical
    strategy: str = "serial"            # serial|parallel|hedged|dag
    max_cost: Optional[float] = None
    max_energy_j: Optional[float] = None
    max_memory_mb: Optional[float] = None
    privacy_tier: str = "internal"      # public|internal|confidential|restricted
    hedge_delay_ms: float = 50.0
    parallel_width: int = 3
    fast_path_probability: float = 0.97
    early_exit_delta: Optional[float] = None
    record: bool = False                # record per-rung results for replay
    seed: Optional[int] = None

    def __post_init__(self):
        if self.qos not in ("best_effort", "standard", "priority", "critical"):
            raise PolicyError(f"unknown qos class: {self.qos!r}")
        if self.strategy not in ("serial", "parallel", "hedged", "dag"):
            raise PolicyError(f"unknown routing strategy: {self.strategy!r}")
        if self.privacy_tier not in ("public", "internal", "confidential",
                                     "restricted"):
            raise PolicyError(f"unknown privacy tier: {self.privacy_tier!r}")
        for name in ("max_cost", "max_energy_j", "max_memory_mb",
                     "hedge_delay_ms"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise PolicyError(f"{name} must be non-negative, got {value}")
        if self.parallel_width < 1:
            raise PolicyError("parallel_width must be >= 1")
        if not 0.0 <= self.fast_path_probability <= 1.0:
            raise PolicyError("fast_path_probability must be in [0,1]")
        if (self.early_exit_delta is not None
                and not 0.0 <= self.early_exit_delta <= 1.0):
            raise PolicyError("early_exit_delta must be in [0,1]")


@dataclass
class RouterContext:
    """Everything a planner may inspect. Raw state stays out; only the
    *shape* of the state (key names, spec, policy, options) is exposed so
    planning never leaks sensitive values into plans or logs."""

    spec: DecisionSpec
    policy: DecisionPolicy
    options: RoutingOptions = field(default_factory=RoutingOptions)
    state_keys: Tuple[str, ...] = ()
    state_size_hint: int = 0

    @classmethod
    def from_request(cls, state: Mapping[str, Any], spec: DecisionSpec,
                     policy: Optional[DecisionPolicy] = None,
                     options: Optional[RoutingOptions] = None,
                     ) -> "RouterContext":
        keys = tuple(sorted(str(k) for k in state.keys()))
        return cls(spec=spec, policy=policy or DecisionPolicy(),
                   options=options or RoutingOptions(),
                   state_keys=keys, state_size_hint=len(keys))


@dataclass
class RungNode:
    """One executable step of a routing plan."""

    backend_name: str
    min_confidence: float = 0.0
    latency_budget_ms: Optional[float] = None
    mode: RungMode = RungMode.SERIAL
    why: str = ""                       # planner rationale, human readable
    params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not 0.0 <= self.min_confidence <= 1.0:
            raise SpecError(
                f"min_confidence must be in [0,1], got {self.min_confidence}")
        if self.latency_budget_ms is not None and self.latency_budget_ms < 0:
            raise SpecError("latency_budget_ms must be non-negative")
        if isinstance(self.mode, str):
            self.mode = RungMode(self.mode)

    def to_ladder_rung(self) -> LadderRung:
        return LadderRung(self.backend_name, self.min_confidence,
                          self.latency_budget_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backend_name": self.backend_name,
            "min_confidence": self.min_confidence,
            "latency_budget_ms": self.latency_budget_ms,
            "mode": self.mode.value,
            "why": self.why,
            "params": dict(self.params),
        }


@dataclass
class RoutingPlan:
    """An ordered, inspectable execution plan produced by a planner."""

    nodes: List[RungNode]
    strategy: RungMode = RungMode.SERIAL
    created_by: str = "unknown"
    rationale: List[str] = field(default_factory=list)

    def __post_init__(self):
        if isinstance(self.strategy, str):
            self.strategy = RungMode(self.strategy)

    @property
    def fingerprint(self) -> str:
        """Stable sha256 over the canonical plan; identical plans hash alike."""
        canonical = json.dumps(
            [n.to_dict() for n in self.nodes] + [self.strategy.value],
            sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "strategy": self.strategy.value,
            "created_by": self.created_by,
            "rationale": list(self.rationale),
            "nodes": [n.to_dict() for n in self.nodes],
        }


@dataclass
class RoutingDecision:
    """The full outcome of executing a plan: decision + plan + audit."""

    result: DecisionResult
    plan: RoutingPlan
    audit: List[Dict[str, Any]]
    accepted_rung: int


class RungPlanner(Protocol):
    """Builds a :class:`RoutingPlan` from a :class:`RouterContext`."""

    def plan(self, ctx: RouterContext) -> RoutingPlan: ...


class RungExecutor(Protocol):
    """Walks a :class:`RoutingPlan` and returns a :class:`RoutingDecision`."""

    def execute(self, router: "LadderRouterV2", plan: RoutingPlan,
                state: Mapping[str, Any], ctx: RouterContext
                ) -> RoutingDecision: ...


class SerialPlanExecutor:
    """Default executor: walk rungs in order using the v1 climb semantics.

    Reuses :meth:`LadderRouterV2.skip_reason` and
    :meth:`LadderRouterV2._attempt` so v2 serial execution is
    behavior-identical to the v1 ladder.
    """

    def execute(self, router: "LadderRouterV2", plan: RoutingPlan,
                state: Mapping[str, Any], ctx: RouterContext
                ) -> RoutingDecision:
        import time

        from hugrgate.errors import Abstention
        from hugrgate.ladder import (RUNG_ABSTAINED, RUNG_ACCEPTED,
                                     RUNG_BELOW_CONFIDENCE,
                                     RUNG_SKIPPED_LATENCY,
                                     RUNG_SKIPPED_PRIVACY,
                                     RUNG_SKIPPED_UNKNOWN,
                                     RUNG_SKIPPED_UNSUPPORTED,
                                     LadderAuditEntry)

        _SKIP = {RUNG_SKIPPED_UNKNOWN, RUNG_SKIPPED_UNSUPPORTED,
                 RUNG_SKIPPED_PRIVACY, RUNG_SKIPPED_LATENCY}

        audit: List[LadderAuditEntry] = []
        started = time.perf_counter()
        policy = ctx.policy

        for i, node in enumerate(plan.nodes):
            backend = router.registry.get(node.backend_name)
            if backend is None:
                audit.append(LadderAuditEntry(
                    i, node.backend_name, RUNG_SKIPPED_UNKNOWN,
                    detail="backend not in registry"))
                continue
            skip = router.skip_reason(backend, node.to_ladder_rung(),
                                        ctx.spec, policy, started)
            if skip is not None:
                audit.append(LadderAuditEntry(
                    i, backend.name, skip[0], detail=skip[1]))
                continue
            result = router._attempt(backend, state, ctx.spec, None, audit, i)
            if result is None:
                continue
            gate = max(node.min_confidence, policy.minimum_probability)
            if result.probability >= gate:
                audit[-1].outcome = RUNG_ACCEPTED
                audit[-1].detail = (f"probability {result.probability:.3f} "
                                    f"cleared gate {gate:.3f}")
                router._log_attempt(state, ctx.spec, result, policy, gate)
                result.metadata["routing_plan"] = plan.to_dict()
                result.metadata["ladder_trace"] = [e.to_dict() for e in audit]
                result.metadata["ladder_rung"] = i
                result.metadata["ladder_backend"] = backend.name
                router.last_audit = audit
                router.note_latencies(audit)
                return RoutingDecision(
                    result=result, plan=plan,
                    audit=[e.to_dict() for e in audit], accepted_rung=i)

            audit[-1].outcome = RUNG_BELOW_CONFIDENCE
            audit[-1].detail = (f"probability {result.probability:.3f} "
                                f"below gate {gate:.3f}; climbing")
            router._log_attempt(state, ctx.spec, result, policy, gate)

        router.last_audit = audit
        router.note_latencies(audit)
        raise Abstention(
            "routing plan exhausted: no rung cleared its gate",
            reason="ladder_exhausted",
            ladder_trace=[e.to_dict() for e in audit],
            plan_fingerprint=plan.fingerprint)


class LadderRouterV2(LadderRouter):
    """v2 router: plan first, then execute.

    The default planner translates the configured ladders into a serial
    :class:`RoutingPlan`; later slices install richer planners (dynamic
    construction, per-request synthesis, DAGs) and executors (parallel,
    hedged). :meth:`decide` keeps the v1 signature and result contract so
    existing callers are unaffected.
    """

    def __init__(self, *args, planner: Optional[RungPlanner] = None,
                 executor: Optional[RungExecutor] = None,
                 latency_tracker=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.planner: RungPlanner = planner or _DefaultPlanner(self)
        self.executor: RungExecutor = executor or SerialPlanExecutor()
        self.latency_tracker = latency_tracker
        self.last_plan: Optional[RoutingPlan] = None

    def note_latencies(self, audit) -> None:
        """Feed measured rung latencies into the tracker, if one is set."""
        if self.latency_tracker is None:
            return
        for entry in audit:
            latency = entry.get("latency_ms") if isinstance(entry, dict) \
                else entry.latency_ms
            name = entry.get("backend_name") if isinstance(entry, dict) \
                else entry.backend_name
            if latency and latency > 0:
                self.latency_tracker.record(name, latency)

    def build_plan(self, state: Mapping[str, Any], spec: DecisionSpec,
                   policy: Optional[DecisionPolicy] = None,
                   options: Optional[RoutingOptions] = None
                   ) -> Tuple[RoutingPlan, RouterContext]:
        """Inspectable plan construction — no backend is touched."""
        ctx = RouterContext.from_request(state, spec, policy, options)
        plan = self.planner.plan(ctx)
        self.last_plan = plan
        return plan, ctx

    def decide(self, state: Mapping[str, Any], spec: DecisionSpec,
               policy: Optional[DecisionPolicy] = None,
               context: Optional[Mapping[str, Any]] = None,
               options: Optional[RoutingOptions] = None) -> DecisionResult:
        """Build the plan, execute it, return the winning result."""
        plan, ctx = self.build_plan(state, spec, policy, options)
        decision = self.executor.execute(self, plan, state, ctx)
        return decision.result


class _DefaultPlanner:
    """Translate configured v1 ladders into a serial v2 plan."""

    def __init__(self, router: LadderRouterV2):
        self._router = router

    def plan(self, ctx: RouterContext) -> RoutingPlan:
        rungs = self._router.ladder_for(ctx.spec)
        nodes = [RungNode(r.backend_name, r.min_confidence,
                          r.latency_budget_ms,
                          why=f"configured ladder rung for {ctx.spec.type}")
                 for r in rungs]
        return RoutingPlan(nodes=nodes, strategy=RungMode.SERIAL,
                           created_by="LadderRouterV2.default",
                           rationale=[f"{len(nodes)} configured rungs"])
