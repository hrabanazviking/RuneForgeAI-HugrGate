"""Route simulation. Slice 071.

:func:`simulate` dry-runs a routing plan against backend *estimates* —
no backend is ever called. It answers, before spending anything:

- which rungs would be skipped and why (reusing the router's real
  :meth:`skip_reason`, so predictions match execution);
- per-rung estimated latency, cost, energy, memory, and capability;
- totals for the full climb;
- a what-if table: "if rung k wins, the climb costs X ms / Y money /
  Z joules".

What simulation honestly cannot do: predict *which* rung will clear its
gate — that depends on the live result probabilities. The report says
so explicitly instead of inventing a winner. Capability scores (slice
054) are reported as the best available proxy for rung quality, labeled
as such.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.routing.architecture import LadderRouterV2, RouterContext, RoutingPlan
from hugrgate.routing.capability import CapabilityScorer
from hugrgate.routing.energy import EnergyModel
from hugrgate.routing.memory import MemoryModel

__all__ = [
    "SimulatedRung",
    "SimulationReport",
    "simulate",
]


@dataclass
class SimulatedRung:
    backend_name: str
    rung_index: int
    would_skip: bool
    skip_reason: str = ""
    est_latency_ms: float = 0.0
    est_cost: float = 0.0
    est_energy_j: float = 0.0
    est_memory_mb: float = 0.0
    capability: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_name": self.backend_name,
            "rung_index": self.rung_index,
            "would_skip": self.would_skip,
            "skip_reason": self.skip_reason,
            "est_latency_ms": round(self.est_latency_ms, 3),
            "est_cost": round(self.est_cost, 6),
            "est_energy_j": round(self.est_energy_j, 6),
            "est_memory_mb": round(self.est_memory_mb, 3),
            "capability": self.capability,
        }


@dataclass
class SimulationReport:
    plan_fingerprint: str
    rungs: list[SimulatedRung] = field(default_factory=list)
    what_if_win: list[dict[str, Any]] = field(default_factory=list)
    note: str = ("simulation predicts skips and resource use from "
                 "estimates; it cannot predict which rung will clear "
                 "its gate.")

    def totals(self) -> dict[str, float]:
        runnable = [r for r in self.rungs if not r.would_skip]
        return {
            "runnable_rungs": len(runnable),
            "skipped_rungs": len(self.rungs) - len(runnable),
            "est_total_latency_ms": round(
                sum(r.est_latency_ms for r in runnable), 3),
            "est_total_cost": round(sum(r.est_cost for r in runnable), 6),
            "est_total_energy_j": round(
                sum(r.est_energy_j for r in runnable), 6),
            "est_peak_memory_mb": round(
                max([r.est_memory_mb for r in runnable] + [0.0]), 3),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_fingerprint": self.plan_fingerprint,
            "rungs": [r.to_dict() for r in self.rungs],
            "what_if_win": self.what_if_win,
            "totals": self.totals(),
            "note": self.note,
        }


def simulate(router: LadderRouterV2, plan: RoutingPlan,
             state: Mapping[str, Any], ctx: RouterContext,
             energy_model: EnergyModel | None = None,
             memory_model: MemoryModel | None = None,
             ) -> SimulationReport:
    """Dry-run ``plan`` against estimates. Never calls a backend."""
    energy_model = energy_model or EnergyModel()
    memory_model = memory_model or MemoryModel()
    scorer = CapabilityScorer()
    started = time.perf_counter()
    policy = ctx.policy

    rungs: list[SimulatedRung] = []
    for i, node in enumerate(plan.nodes):
        backend = router.registry.get(node.backend_name)
        if backend is None:
            rungs.append(SimulatedRung(
                node.backend_name, i, True,
                skip_reason="backend not in registry"))
            continue
        skip = router.skip_reason(backend, node.to_ladder_rung(),
                                  ctx.spec, policy, started)
        if skip is not None:
            rungs.append(SimulatedRung(
                node.backend_name, i, True,
                skip_reason=f"{skip[0]}: {skip[1]}"))
            continue
        rungs.append(SimulatedRung(
            node.backend_name, i, False,
            est_latency_ms=float(backend.estimated_latency()),
            est_cost=float(backend.estimated_cost()),
            est_energy_j=energy_model.estimate_j(backend),
            est_memory_mb=memory_model.estimate_mb(backend),
            capability=scorer.score(backend, ctx).value,
        ))

    # What-if table: cumulative spend if rung k (runnable) wins.
    what_if: list[dict[str, Any]] = []
    cum_lat = cum_cost = cum_energy = 0.0
    for r in rungs:
        if r.would_skip:
            continue
        cum_lat += r.est_latency_ms
        cum_cost += r.est_cost
        cum_energy += r.est_energy_j
        what_if.append({
            "if_rung_wins": r.rung_index,
            "backend_name": r.backend_name,
            "cumulative_latency_ms": round(cum_lat, 3),
            "cumulative_cost": round(cum_cost, 6),
            "cumulative_energy_j": round(cum_energy, 6),
        })

    return SimulationReport(plan_fingerprint=plan.fingerprint,
                            rungs=rungs, what_if_win=what_if)
