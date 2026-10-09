"""Route replay. Slice 070.

A recorded climb can be replayed *without touching any backend*: 
:class:`RecordingExecutor` wraps any executor and captures the plan,
per-rung outcomes (probabilities, latencies, skip reasons), and the
winning result into a :class:`RouteRecording` (JSON-serializable).
:func:`replay` / :class:`ReplayExecutor` then walk the recorded plan
using the recorded probabilities instead of calling backends, applying
the recorded policy's gates — reproducing the recorded winner
deterministically.

Recorded skip outcomes are authoritative: replay never consults the
registry, so even an empty registry replays faithfully. The plan
fingerprint is verified before replay; tampering raises ``SpecError``.

Limitations (documented, not hidden): replay reproduces the *routing
outcome* (winner, probability, audit), not wall-clock latencies —
latencies are recorded facts, not re-measured. Only successful
decisions are recordable; abstentions carry no winner to reproduce.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import Abstention, SpecError
from hugrgate.ladder import RUNG_ACCEPTED, RUNG_BELOW_CONFIDENCE, LadderAuditEntry
from hugrgate.result import DecisionResult
from hugrgate.routing.architecture import (
    LadderRouterV2,
    RouterContext,
    RoutingDecision,
    RoutingPlan,
    RungExecutor,
    RungMode,
    RungNode,
)

__all__ = [
    "RecordingExecutor",
    "ReplayExecutor",
    "RouteRecording",
    "replay",
]


@dataclass
class RouteRecording:
    """A JSON-serializable capture of one executed climb."""

    plan: dict[str, Any]
    plan_fingerprint: str
    spec_type: str
    spec_options: list[str]
    minimum_probability: float
    rung_outcomes: list[dict[str, Any]] = field(default_factory=list)
    winner_index: int | None = None
    winner_result: dict[str, Any] | None = None
    recorded_at: float = field(default_factory=time.time)

    def to_json(self) -> dict[str, Any]:
        return {
            "plan": self.plan,
            "plan_fingerprint": self.plan_fingerprint,
            "spec_type": self.spec_type,
            "spec_options": list(self.spec_options),
            "minimum_probability": self.minimum_probability,
            "rung_outcomes": [dict(o) for o in self.rung_outcomes],
            "winner_index": self.winner_index,
            "winner_result": (dict(self.winner_result)
                              if self.winner_result else None),
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RouteRecording:
        return cls(
            plan=data["plan"],
            plan_fingerprint=data["plan_fingerprint"],
            spec_type=data["spec_type"],
            spec_options=data["spec_options"],
            minimum_probability=data["minimum_probability"],
            rung_outcomes=data["rung_outcomes"],
            winner_index=data["winner_index"],
            winner_result=data["winner_result"],
            recorded_at=data.get("recorded_at", 0.0),
        )


class RecordingExecutor(RungExecutor):
    """Wrap an executor; capture a replayable recording of each decision."""

    def __init__(self, inner: RungExecutor):
        self.inner = inner
        self.last_recording: RouteRecording | None = None

    def execute(self, router: LadderRouterV2, plan: RoutingPlan,
                state: Mapping, ctx: RouterContext) -> RoutingDecision:
        decision = self.inner.execute(router, plan, state, ctx)
        outcomes = [
            {
                "rung_index": e["rung_index"],
                "backend_name": e["backend_name"],
                "outcome": e["outcome"],
                "probability": e.get("probability"),
                "latency_ms": e.get("latency_ms", 0.0),
                "detail": e.get("detail", ""),
            }
            for e in decision.audit
        ]
        self.last_recording = RouteRecording(
            plan=plan.to_dict(),
            plan_fingerprint=plan.fingerprint,
            spec_type=ctx.spec.type,
            spec_options=list(ctx.spec.options or []),
            minimum_probability=ctx.policy.minimum_probability,
            rung_outcomes=outcomes,
            winner_index=decision.accepted_rung,
            winner_result=decision.result.to_dict(),
        )
        return decision


class ReplayExecutor(RungExecutor):
    """Replay a :class:`RouteRecording` without touching any backend."""

    def __init__(self, recording: RouteRecording):
        self.recording = recording

    def execute(self, router: LadderRouterV2, plan: RoutingPlan,
                state: Mapping, ctx: RouterContext) -> RoutingDecision:
        return replay(self.recording)


def _rebuild_plan(data: dict[str, Any]) -> RoutingPlan:
    nodes = []
    for nd in data["nodes"]:
        nodes.append(RungNode(
            nd["backend_name"], nd["min_confidence"],
            nd["latency_budget_ms"], RungMode(nd["mode"]),
            why=nd.get("why", ""), params=dict(nd.get("params", {}))))
    return RoutingPlan(nodes=nodes,
                       strategy=RungMode(data["strategy"]),
                       created_by=data.get("created_by", "replay"),
                       rationale=list(data.get("rationale", [])))


def replay(recording: RouteRecording) -> RoutingDecision:
    """Deterministically reproduce a recorded decision. No backends run."""
    plan = _rebuild_plan(recording.plan)
    if plan.fingerprint != recording.plan_fingerprint:
        raise SpecError(
            "recording tampered: plan fingerprint mismatch "
            f"({plan.fingerprint} != {recording.plan_fingerprint})")
    if recording.winner_index is None or recording.winner_result is None:
        raise SpecError("recording has no winner to replay")

    by_index = {o["rung_index"]: o for o in recording.rung_outcomes}
    audit: list[LadderAuditEntry] = []
    gate_policy = recording.minimum_probability

    for i, node in enumerate(plan.nodes):
        recorded = by_index.get(i)
        if recorded is None:
            raise SpecError(f"recording missing rung index {i}")
        outcome = recorded["outcome"]
        if outcome not in (RUNG_ACCEPTED, RUNG_BELOW_CONFIDENCE):
            # skips, errors, abstentions: authoritative as recorded
            audit.append(LadderAuditEntry(
                i, recorded["backend_name"], outcome,
                detail=recorded.get("detail", "") + " [replay]",
                probability=recorded.get("probability"),
                latency_ms=recorded.get("latency_ms", 0.0)))
            continue
        prob = recorded.get("probability")
        if prob is None:
            raise SpecError(f"recording missing probability for rung {i}")
        gate = max(node.min_confidence, gate_policy)
        if prob >= gate and i == recording.winner_index:
            result = DecisionResult(**recording.winner_result)
            audit.append(LadderAuditEntry(
                i, recorded["backend_name"], RUNG_ACCEPTED,
                detail=(f"replay: probability {prob:.3f} cleared gate "
                        f"{gate:.3f}"),
                probability=prob,
                latency_ms=recorded.get("latency_ms", 0.0)))
            result.metadata["replayed"] = True
            result.metadata["routing_plan"] = plan.to_dict()
            result.metadata["ladder_trace"] = [e.to_dict() for e in audit]
            return RoutingDecision(result=result, plan=plan,
                                   audit=[e.to_dict() for e in audit],
                                   accepted_rung=i)
        audit.append(LadderAuditEntry(
            i, recorded["backend_name"], RUNG_BELOW_CONFIDENCE,
            detail=(f"replay: probability {prob:.3f} below gate {gate:.3f}"),
            probability=prob,
            latency_ms=recorded.get("latency_ms", 0.0)))

    raise Abstention(
        "replay exhausted without reproducing the recorded winner",
        reason="replay_diverged",
        ladder_trace=[e.to_dict() for e in audit],
        plan_fingerprint=plan.fingerprint)
