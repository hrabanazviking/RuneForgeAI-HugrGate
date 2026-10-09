"""Dynamic rung construction. Slice 052.

Where the v1 ladder (and the 051 default planner) climb a *statically
configured* rung list, :class:`RungBuilder` constructs the rung list at
request time from the live registry: it enumerates backends, applies the
policy's allow/block lists, drops backends that cannot serve the spec or
that the privacy posture forbids, and orders survivors by expected price
of admission (cost, then latency), with preferred backends floated first.

:class:`DynamicRungPlanner` adapts the builder to the
:class:`~hugrgate.routing.architecture.RungPlanner` protocol so a
:class:`~hugrgate.routing.architecture.LadderRouterV2` can build a fresh
ladder per request instead of reusing a configured one.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from hugrgate.backend import Backend
from hugrgate.routing.architecture import (
    RouterContext,
    RoutingPlan,
    RungMode,
    RungNode,
    RungPlanner,
)

__all__ = [
    "DynamicRungPlanner",
    "RungBuilder",
    "RungFilter",
]

#: A predicate deciding whether a backend may become a rung.
RungFilter = Callable[[Backend, RouterContext], bool]


def _allowlist_filter(backend: Backend, ctx: RouterContext) -> bool:
    allowed = ctx.policy.allowed_backends
    return allowed is None or backend.name in allowed


def _supports_filter(backend: Backend, ctx: RouterContext) -> bool:
    return backend.supports(ctx.spec)


def _privacy_prefilter(backend: Backend, ctx: RouterContext) -> bool:
    # Remote backends are pruned at plan time when the policy forbids them.
    # The executor's skip_reason re-checks at run time (belt and suspenders:
    # policy could change between planning and execution).
    return ctx.policy.backend_allowed(backend.name, backend.is_remote)


class RungBuilder:
    """Construct rung lists dynamically from the registry.

    Parameters
    ----------
    extra_filters: additional :data:`RungFilter` callables applied after the
        built-in allowlist/support/privacy filters. Later slices (hardware,
        availability, memory) plug in here.
    order: sort key preference — ``"cost"`` (then latency), ``"latency"``
        (then cost), or ``"capability"`` (slice-054 scorer, cost breaks
        ties).
    max_rungs: cap on the constructed ladder length.
    """

    def __init__(self, extra_filters: Sequence[RungFilter] = (),
                 order: str = "cost",
                 max_rungs: int | None = None):
        if order not in ("cost", "latency", "capability"):
            raise ValueError(f"unknown rung order: {order!r}")
        if max_rungs is not None and max_rungs < 0:
            raise ValueError("max_rungs must be non-negative")
        self.extra_filters = list(extra_filters)
        self.order = order
        self.max_rungs = max_rungs

    def _filters(self) -> list[RungFilter]:
        return [_allowlist_filter, _supports_filter, _privacy_prefilter,
                *self.extra_filters]

    def candidates(self, registry, ctx: RouterContext) -> list[Backend]:
        """Backends surviving every filter, cheapest-first."""
        survivors = []
        for name in registry.list():
            backend = registry.get(name)
            if backend is None:
                continue
            if all(f(backend, ctx) for f in self._filters()):
                survivors.append(backend)
        preferred = set(ctx.policy.preferred_backends or ())
        if self.order == "cost":
            def key(b: Backend) -> tuple:
                return (b.estimated_cost(), b.estimated_latency())
        elif self.order == "latency":
            def key(b: Backend) -> tuple:
                return (b.estimated_latency(), b.estimated_cost())
        else:  # capability — highest scored first, cost breaks ties
            from hugrgate.routing.capability import CapabilityScorer
            scorer = CapabilityScorer()
            scores = {b.name: scorer.score(b, ctx).value
                      for b in survivors}
            def key(b: Backend) -> tuple:
                return (-scores[b.name], b.estimated_cost())
        survivors.sort(key=lambda b: (b.name not in preferred, key(b)))
        return survivors

    def build(self, registry, ctx: RouterContext,
              min_confidence: float | None = None) -> list[RungNode]:
        """Build the rung list: one node per surviving backend."""
        gate = (min_confidence if min_confidence is not None
                else ctx.policy.minimum_probability)
        nodes = [
            RungNode(
                backend.name,
                min_confidence=gate,
                latency_budget_ms=ctx.policy.maximum_latency_ms,
                mode=RungMode.SERIAL,
                why=(f"dynamic rung: supports {ctx.spec.type}, "
                     f"est. cost {backend.estimated_cost():.4f}, "
                     f"est. latency {backend.estimated_latency():.1f}ms"),
            )
            for backend in self.candidates(registry, ctx)
        ]
        if self.max_rungs is not None:
            nodes = nodes[:self.max_rungs]
        return nodes


class DynamicRungPlanner(RungPlanner):
    """A planner that builds a fresh ladder per request via :class:`RungBuilder`."""

    def __init__(self, registry, builder: RungBuilder | None = None):
        self.registry = registry
        self.builder = builder or RungBuilder()

    def plan(self, ctx: RouterContext) -> RoutingPlan:
        nodes = self.builder.build(self.registry, ctx)
        return RoutingPlan(
            nodes=nodes,
            strategy=RungMode.SERIAL,
            created_by="DynamicRungPlanner",
            rationale=[f"{len(nodes)} rungs built dynamically from registry"],
        )
