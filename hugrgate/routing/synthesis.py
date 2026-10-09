"""Per-request ladder synthesis. Slice 053.

Slice 052 builds rungs dynamically from the registry; synthesis goes one
step further and *composes* the plan for this exact request: it weighs
each candidate against the request's QoS posture, splits the policy's
latency budget fairly across the plan, caps ladder depth by QoS class,
and records why each rung earned its position. The same registry under a
`best_effort` request and under a `critical` request yields different
ladders — that is the point.

The capability heuristic here is deliberately small; slice 054 promotes
it into a full :class:`CapabilityScorer`, which the synthesizer then
imports.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from hugrgate.backend import Backend
from hugrgate.routing.architecture import (RouterContext, RungMode, RungNode,
                                            RungPlanner, RoutingPlan)
from hugrgate.routing.rungs import RungBuilder

__all__ = [
    "QOS_DEPTH_CAPS",
    "QOS_WEIGHTS",
    "score_capability",
    "LadderSynthesizer",
]

#: Max rungs a synthesized ladder may hold, by QoS class.
QOS_DEPTH_CAPS: Dict[str, int] = {
    "best_effort": 2,
    "standard": 4,
    "priority": 6,
    "critical": 8,
}

#: Blending weights (capability, 1/latency, 1/cost) by QoS class.
QOS_WEIGHTS: Dict[str, tuple] = {
    "best_effort": (0.2, 0.4, 0.4),
    "standard": (0.4, 0.3, 0.3),
    "priority": (0.6, 0.25, 0.15),
    "critical": (0.8, 0.15, 0.05),
}


def score_capability(backend: Backend, ctx: RouterContext) -> float:
    """Heuristic capability score in [0,1] for this backend on this request.

    Rewards: spec-type support (required — 0 without it), declared accuracy
    or reliability claims in ``capabilities()``, and calibrated backends.
    Slice 054 replaces this with a scored, reasoned model.
    """
    if not backend.supports(ctx.spec):
        return 0.0
    caps = backend.capabilities() or {}
    score = 0.5  # supports the spec: baseline competence
    for key in ("accuracy", "reliability", "quality"):
        value = caps.get(key)
        if isinstance(value, (int, float)):
            score = max(score, min(1.0, float(value)))
    cal = backend.calibration_info() or {}
    if cal.get("calibrated"):
        score = min(1.0, score + 0.1)
    if caps.get("spec_types") and ctx.spec.type in caps["spec_types"]:
        score = min(1.0, score + 0.05)
    return round(score, 4)


class LadderSynthesizer(RungPlanner):
    """Compose a per-request ladder from live candidates.

    Parameters
    ----------
    registry: backends to synthesize from.
    builder: candidate source (defaults to a plain :class:`RungBuilder`).
    """

    def __init__(self, registry, builder: Optional[RungBuilder] = None):
        self.registry = registry
        self.builder = builder or RungBuilder()

    def plan(self, ctx: RouterContext) -> RoutingPlan:
        candidates = self.builder.candidates(self.registry, ctx)
        weights = QOS_WEIGHTS[ctx.options.qos]
        cap = QOS_DEPTH_CAPS[ctx.options.qos]

        scored = [(self._blend(b, ctx, weights), b) for b in candidates]
        scored.sort(key=lambda t: (-t[0], t[1].name))
        chosen = scored[:cap]

        budget = ctx.policy.maximum_latency_ms
        nodes: List[RungNode] = []
        rationale: List[str] = []
        for rank, (score, backend) in enumerate(chosen):
            rung_budget = (budget / len(chosen)) if budget else None
            node = RungNode(
                backend.name,
                min_confidence=ctx.policy.minimum_probability,
                latency_budget_ms=rung_budget,
                mode=RungMode(ctx.options.strategy),
                why=(f"rank {rank}: blended score {score:.3f} "
                     f"(cap={score_capability(backend, ctx):.2f}, "
                     f"lat={backend.estimated_latency():.1f}ms, "
                     f"cost={backend.estimated_cost():.4f})"),
                params={"blended_score": score,
                        "capability": score_capability(backend, ctx)},
            )
            nodes.append(node)
            rationale.append(f"{backend.name}: score {score:.3f} — {node.why}")

        strategy = RungMode(ctx.options.strategy)
        return RoutingPlan(
            nodes=nodes,
            strategy=strategy,
            created_by="LadderSynthesizer",
            rationale=rationale or ["no candidates survived filtering"],
        )

    @staticmethod
    def _blend(backend: Backend, ctx: RouterContext,
               weights: tuple) -> float:
        w_cap, w_lat, w_cost = weights
        cap = score_capability(backend, ctx)
        lat = 1.0 / (1.0 + backend.estimated_latency() / 100.0)
        cost = 1.0 / (1.0 + backend.estimated_cost() * 100.0)
        return round(w_cap * cap + w_lat * lat + w_cost * cost, 4)
