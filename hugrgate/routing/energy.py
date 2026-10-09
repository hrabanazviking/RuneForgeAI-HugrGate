"""Energy-aware routing. Slice 058.

Inference costs energy, and energy is a budget like latency or money.
:class:`EnergyModel` estimates joules per rung as

    energy_j = latency_s × power_watts

where ``power_watts`` comes from ``backend.hardware_requirements()`` when
declared, else from documented class defaults. :class:`EnergyLedger`
tracks a per-request joule budget (``options.max_energy_j``); 
:class:`EnergyAwarePlanner` prunes rungs the budget cannot cover; the
router feeds measured latencies back through ``note_energy``.

Power-draw assumptions (stated, not hidden):
- local backend without a declared draw: 65 W (typical desktop CPU);
- remote backend without a declared draw: 5 W client-side (NIC + idle
  CPU share). Server-side energy is out of scope and documented as such —
  the model compares *client-attributable* energy, which is what routing
  on this machine can actually control.
- a backend may override everything with ``estimated_energy_j()``.

The reproducible measurement artifact lives in
``benchmarks/routing_energy_058.py`` → ``benchmarks/routing_energy_058.json``.
"""

from __future__ import annotations

from typing import List, Optional

from hugrgate.backend import Backend
from hugrgate.routing.architecture import (RouterContext, RungNode,
                                            RungPlanner, RoutingPlan)

__all__ = [
    "EnergyModel",
    "EnergyLedger",
    "EnergyAwarePlanner",
    "DEFAULT_LOCAL_WATTS",
    "DEFAULT_REMOTE_WATTS",
]

#: Assumed draw for a local backend that declares no power figure.
DEFAULT_LOCAL_WATTS = 65.0
#: Assumed client-side draw for a remote backend that declares no figure.
DEFAULT_REMOTE_WATTS = 5.0


class EnergyModel:
    """Joule estimates per backend from latency × power draw."""

    def __init__(self, local_watts: float = DEFAULT_LOCAL_WATTS,
                 remote_watts: float = DEFAULT_REMOTE_WATTS):
        if local_watts <= 0 or remote_watts <= 0:
            raise ValueError("power draws must be positive")
        self.local_watts = local_watts
        self.remote_watts = remote_watts

    def power_watts(self, backend: Backend) -> float:
        declared = (backend.hardware_requirements() or {}).get("power_watts")
        if isinstance(declared, (int, float)) and declared > 0:
            return float(declared)
        return self.remote_watts if backend.is_remote else self.local_watts

    def estimate_j(self, backend: Backend,
                   latency_ms: Optional[float] = None) -> float:
        """Joules for one rung execution.

        Uses the backend's own ``estimated_energy_j()`` when provided,
        else latency (measured when given, declared otherwise) × power.
        """
        custom = getattr(backend, "estimated_energy_j", None)
        if callable(custom):
            value = custom()
            if isinstance(value, (int, float)) and value >= 0:
                return float(value)
        latency = (latency_ms if latency_ms is not None
                   else backend.estimated_latency())
        return round(max(0.0, latency) / 1000.0 * self.power_watts(backend), 6)


class EnergyLedger:
    """Per-request joule accounting: reserve at plan time, spend at run time."""

    def __init__(self, budget_j: Optional[float],
                 model: Optional[EnergyModel] = None):
        if budget_j is not None and budget_j < 0:
            raise ValueError(f"budget must be non-negative, got {budget_j}")
        self.budget_j = budget_j
        self.model = model or EnergyModel()
        self.reserved = 0.0
        self.spent = 0.0

    @property
    def remaining(self) -> Optional[float]:
        if self.budget_j is None:
            return None
        return max(0.0, self.budget_j - self.reserved - self.spent)

    def can_afford(self, joules: float) -> bool:
        remaining = self.remaining
        if remaining is None:
            return True
        return joules <= remaining

    def reserve(self, backend_name: str, joules: float) -> bool:
        if not self.can_afford(joules):
            return False
        self.reserved += joules
        return True

    def spend(self, joules: float) -> None:
        if joules < 0:
            raise ValueError(f"spend must be non-negative, got {joules}")
        self.spent += joules

    def to_dict(self) -> dict:
        return {
            "budget_j": self.budget_j,
            "reserved_j": round(self.reserved, 6),
            "spent_j": round(self.spent, 6),
            "remaining_j": (round(self.remaining, 6)
                            if self.remaining is not None else None),
        }


class EnergyAwarePlanner(RungPlanner):
    """Wrap a planner; prune rungs the joule budget cannot cover.

    The budget is per-request: ``budget_j`` when given, else
    ``ctx.options.max_energy_j``. A fresh ledger is minted per plan so
    reservations never leak across requests.
    """

    def __init__(self, inner: RungPlanner, registry,
                 budget_j: Optional[float] = None,
                 model: Optional[EnergyModel] = None):
        if budget_j is not None and budget_j < 0:
            raise ValueError(f"budget_j must be non-negative, got {budget_j}")
        self.inner = inner
        self.registry = registry
        self.budget_j = budget_j
        self.model = model or EnergyModel()

    def plan(self, ctx: RouterContext) -> RoutingPlan:
        plan = self.inner.plan(ctx)
        budget = (self.budget_j if self.budget_j is not None
                  else ctx.options.max_energy_j)
        ledger = EnergyLedger(budget, self.model)
        kept: List[RungNode] = []
        pruned: List[str] = []
        for node in plan.nodes:
            backend = self.registry.get(node.backend_name)
            joules = (ledger.model.estimate_j(backend)
                      if backend is not None else 0.0)
            node.params["energy_estimate_j"] = joules
            if ledger.reserve(node.backend_name, joules):
                kept.append(node)
            else:
                pruned.append(
                    f"{node.backend_name}: est. {joules:.4f}J exceeds "
                    f"remaining {ledger.remaining:.4f}J")
        plan.nodes = kept
        plan.created_by = f"{plan.created_by}+energy"
        plan.rationale.append(
            f"energy ledger: budget={ledger.budget_j}J, "
            f"reserved={ledger.reserved:.4f}J, pruned {len(pruned)}"
            + (": " + "; ".join(pruned) if pruned else ""))
        plan.energy_ledger = ledger  # type: ignore[attr-defined]
        return plan
