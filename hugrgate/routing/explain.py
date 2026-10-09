"""Route explanation. Slice 069.

Audit trails are for machines; this module is for humans.
:func:`explain_plan` narrates a plan *before* execution ("what will be
tried, in what order, and why"); :func:`explain_route` narrates an
executed climb *after* ("what was tried, what happened at each rung,
and why this backend won"); :func:`explain_decision` ties a
:class:`RoutingDecision` together into one readable account.

Every rung outcome the ladder can produce — including the slice-065
``cancelled`` outcome — has a plain-language phrasing. Explanations
never include raw state values: they name backends, gates, budgets,
and reasons, never the data that flowed through.
"""

from __future__ import annotations

from hugrgate.ladder import (
    RUNG_ABSTAINED,
    RUNG_ACCEPTED,
    RUNG_BELOW_CONFIDENCE,
    RUNG_CANCELLED,
    RUNG_ERROR,
    RUNG_SKIPPED_LATENCY,
    RUNG_SKIPPED_PRIVACY,
    RUNG_SKIPPED_UNKNOWN,
    RUNG_SKIPPED_UNSUPPORTED,
    RUNG_UNAVAILABLE,
)
from hugrgate.routing.architecture import RoutingDecision, RoutingPlan

__all__ = [
    "OUTCOME_PHRASES",
    "explain_decision",
    "explain_plan",
    "explain_route",
]

OUTCOME_PHRASES: dict[str, str] = {
    RUNG_ACCEPTED: "accepted — cleared its gate",
    RUNG_BELOW_CONFIDENCE: "below its confidence gate; climbed on",
    RUNG_SKIPPED_UNKNOWN: "skipped — backend not in the registry",
    RUNG_SKIPPED_UNSUPPORTED: "skipped — backend cannot serve this spec",
    RUNG_SKIPPED_PRIVACY: "skipped — blocked by privacy policy",
    RUNG_SKIPPED_LATENCY: "skipped — over the latency budget",
    RUNG_UNAVAILABLE: "failed — backend unavailable",
    RUNG_ERROR: "failed — backend error",
    RUNG_ABSTAINED: "abstained — backend declined to decide",
    RUNG_CANCELLED: "cancelled — hedge straggler dropped after a win",
}


def _phrase(outcome: str) -> str:
    return OUTCOME_PHRASES.get(outcome, outcome.replace("_", " "))


def explain_plan(plan: RoutingPlan) -> str:
    """Narrate a plan before execution."""
    lines = [
        f"Routing plan {plan.fingerprint} "
        f"({plan.strategy.value}, by {plan.created_by}):",
    ]
    if not plan.nodes:
        lines.append("  (empty — nothing to try; the climb will abstain)")
        return "\n".join(lines)
    for i, node in enumerate(plan.nodes):
        bits = [f"rung {i}: {node.backend_name!r}",
                f"gate {node.min_confidence:.2f}"]
        if node.latency_budget_ms is not None:
            bits.append(f"latency budget {node.latency_budget_ms:.0f}ms")
        if node.mode.value != "serial":
            bits.append(f"mode {node.mode.value}")
        lines.append("  " + ", ".join(bits) + ".")
        if node.why:
            lines.append(f"    why: {node.why}")
    for reason in plan.rationale:
        lines.append(f"  note: {reason}")
    return "\n".join(lines)


def explain_route(audit: list[dict], plan: RoutingPlan | None = None,
                  winner: int | None = None) -> str:
    """Narrate an executed climb from its audit trail."""
    if not audit:
        return "No rungs were attempted."
    lines = []
    if plan is not None:
        lines.append(f"Executed plan {plan.fingerprint} "
                     f"({plan.strategy.value}).")
    attempted = [e for e in audit
                 if e["outcome"] not in ("skipped_unknown_backend",
                                         "skipped_unsupported",
                                         "skipped_privacy_blocked",
                                         "skipped_latency_budget")]
    skipped = len(audit) - len(attempted)
    for e in audit:
        line = (f"Rung {e['rung_index']} {e['backend_name']!r}: "
                f"{_phrase(e['outcome'])}")
        if e.get("detail"):
            line += f" ({e['detail']})"
        if e.get("probability") is not None:
            line += f" [p={e['probability']:.3f}]"
        if e.get("latency_ms"):
            line += f" [{e['latency_ms']:.1f}ms]"
        lines.append(line)
    lines.append(f"Summary: {len(attempted)} attempted, {skipped} skipped, "
                 f"{sum(e.get('latency_ms', 0.0) for e in audit):.1f}ms "
                 f"total rung time.")
    if winner is not None:
        won = next((e for e in audit if e["rung_index"] == winner), None)
        if won is not None:
            lines.append(f"Winner: {won['backend_name']!r} at rung {winner}.")
    return "\n".join(lines)


def explain_decision(decision: RoutingDecision) -> str:
    """One readable account of a full routing decision."""
    header = [
        f"Decision: {decision.result.value!r} "
        f"(p={decision.result.probability:.3f}) "
        f"via {decision.result.backend!r}.",
    ]
    body = explain_route(decision.audit, decision.plan,
                         decision.accepted_rung)
    return "\n".join([*header, body])
