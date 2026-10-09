"""Edge-aware backend routing. Slices 180-181.

:class:`EdgeRouter` sits *beside* :class:`hugrgate.core.HugrGate`, not
inside it: it inspects edge conditions (thermal level, power budget,
memory mode) and produces a narrowed candidate list plus an optional
policy overlay. The application then calls
``gate.decide(..., backend_name=...)`` or passes the constrained policy
— core routing semantics and backward compatibility are untouched.

Backends advertise edge costs through :meth:`Backend.hardware_requirements`
under the ``"edge"`` key::

    {"edge": {"power_mw": 1200, "thermal_class": "warm",
              "min_ram_mb": 512}}

Missing keys mean "unknown": the router treats unknown power as
unbounded-but-allowed (it cannot prove infeasibility) and unknown
thermal class as ``"warm"``.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from hugrgate.backend import Backend
from hugrgate.edge.thermal import ThermalGovernor, ThermalLevel
from hugrgate.policy import DecisionPolicy

__all__ = [
    "THERMAL_CLASSES",
    "EdgeRouter",
    "edge_cost_of",
]

#: Ordered thermal classes a backend may declare.
THERMAL_CLASSES = ("cool", "warm", "hot")

#: Thermal classes still routable at each governor level.
_LEVEL_ALLOWS: dict[str, tuple[str, ...]] = {
    "normal": ("cool", "warm", "hot"),
    "warm": ("cool", "warm", "hot"),
    "hot": ("cool", "warm"),
    "critical": ("cool",),
}


def edge_cost_of(backend: Backend) -> dict[str, Any]:
    """The ``"edge"`` cost block of a backend's hardware requirements."""
    reqs = backend.hardware_requirements() or {}
    edge = reqs.get("edge") or {}
    return dict(edge) if isinstance(edge, dict) else {}


class EdgeRouter:
    """Filters/orders backend candidates by live edge conditions."""

    def __init__(self, governor: ThermalGovernor | None = None):
        self._governor = governor

    # -- thermal -----------------------------------------------------------

    def thermal_level(self) -> ThermalLevel:
        if self._governor is None:
            return ThermalLevel.NORMAL
        return self._governor.sample().level

    def _thermal_allows(self, backend: Backend,
                       level: ThermalLevel) -> bool:
        declared = str(edge_cost_of(backend).get("thermal_class", "warm"))
        if declared not in THERMAL_CLASSES:
            declared = "warm"
        return declared in _LEVEL_ALLOWS[level.value]

    # -- routing ------------------------------------------------------------

    def route(self, candidates: list[Backend]) -> list[Backend]:
        """Return candidates ordered by edge fitness, thermally filtered.

        Ordering: coolest thermal class first, then lowest declared
        power, then lowest estimated latency. Backends the current
        thermal level forbids are dropped. An empty input stays empty
        (never invent a candidate); if *every* candidate is thermally
        forbidden, the full list is returned unfiltered so the caller —
        not the router — decides whether to abstain.
        """
        if not candidates:
            return []
        level = self.thermal_level()
        allowed = [b for b in candidates if self._thermal_allows(b, level)]
        pool = allowed or candidates

        def rank(b: Backend) -> tuple[int, float, float]:
            cost = edge_cost_of(b)
            tclass = str(cost.get("thermal_class", "warm"))
            if tclass not in THERMAL_CLASSES:
                tclass = "warm"
            t_rank = THERMAL_CLASSES.index(tclass)
            power = cost.get("power_mw")
            p_rank = float(power) if isinstance(power, (int, float)) else float("inf")
            return (t_rank, p_rank, b.estimated_latency())

        return sorted(pool, key=rank)

    def constrain_policy(self, policy: DecisionPolicy,
                         candidates: list[Backend]) -> DecisionPolicy:
        """Return a copy of ``policy`` narrowed to edge-fit backends.

        The copy pins ``allowed_backends`` to the routed names and, when
        thermally derated below 1.0, tightens ``maximum_latency_ms``
        proportionally (a hot chip must not be asked to wait longer).
        The input policy is never mutated.
        """
        routed = self.route(candidates)
        level = self.thermal_level()
        names = [b.name for b in routed]
        allowed = (set(policy.allowed_backends) & set(names)
                   if policy.allowed_backends else set(names))
        latency = policy.maximum_latency_ms
        if latency is not None and level.derating < 1.0:
            latency = latency * level.derating
        return dataclasses.replace(policy,
                                   allowed_backends=sorted(allowed),
                                   maximum_latency_ms=latency)
