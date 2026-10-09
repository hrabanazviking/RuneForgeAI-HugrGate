"""Per-request ladder synthesis. Slice 053.

Slice 052 builds rungs dynamically from the registry; synthesis goes one
step further and *composes* the plan for this exact request: it weighs
each candidate against the request's QoS posture, splits the policy's
latency budget fairly across the plan, caps ladder depth by QoS class,
and records why each rung earned its position. The same registry under a
`best_effort` request and under a `critical` request yields different
ladders — that is the point.

Capability grading comes from slice 054's :class:`CapabilityScorer`.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from hugrgate.backend import Backend
from hugrgate.routing.architecture import (RouterContext, RungMode, RungNode,
                                            RungPlanner, RoutingPlan)
from hugrgate.routing.capability import CapabilityScorer
from hugrgate.routing.qos import QOS_PROFILES, qos_profile
from hugrgate.routing.rungs import RungBuilder

__all__ = [
    "QOS_DEPTH_CAPS",
    "QOS_WEIGHTS",
    "score_capability",
    "LadderSynthesizer",
]

#: Backward-compatible views over the slice-063 QoS profiles (single source
#: of truth now lives in hugrgate.routing.qos).
QOS_DEPTH_CAPS: Dict[str, int] = {
    c.value: p.depth_cap for c, p in QOS_PROFILES.items()
}
QOS_WEIGHTS: Dict[str, tuple] = {
    c.value: p.weights for c, p in QOS_PROFILES.items()
}


def score_capability(backend: Backend, ctx: RouterContext) -> float:
    """Capability score in [0,1] for this backend on this request.

    Thin wrapper over slice 054's :class:`CapabilityScorer`; kept so
    earlier callers keep working.
    """
    return CapabilityScorer().score(backend, ctx).value


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
        profile = qos_profile(ctx.options.qos)
        weights = profile.weights
        cap = profile.depth_cap

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
