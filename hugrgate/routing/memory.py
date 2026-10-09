"""Memory-aware routing. Slice 059.

Unlike cost or energy, memory is a *peak* constraint, not a cumulative
one: each rung must fit within available memory on its own. 
:class:`MemoryModel` estimates a backend's footprint in megabytes from
``hardware_requirements()["memory_mb"]`` when declared, else an optional
``estimated_memory_mb()`` method, else documented class defaults.
:class:`MemoryAwarePlanner` prunes rungs whose footprint exceeds
``options.max_memory_mb`` and stamps survivors with
``params["memory_estimate_mb"]``.

Memory assumptions (stated, not hidden):
- local backend with no declared figure: 512 MB (a modest in-process
  model runtime);
- remote backend with no declared figure: 0 MB client-side — the memory
  lives on the server, which this machine's routing cannot observe.
"""

from __future__ import annotations

from typing import List, Optional

from hugrgate.backend import Backend
from hugrgate.routing.architecture import (RouterContext, RungNode,
                                            RungPlanner, RoutingPlan)

__all__ = [
    "MemoryModel",
    "MemoryAwarePlanner",
    "DEFAULT_LOCAL_MEMORY_MB",
    "DEFAULT_REMOTE_MEMORY_MB",
]

#: Assumed footprint for a local backend that declares no figure.
DEFAULT_LOCAL_MEMORY_MB = 512.0
#: Assumed client-side footprint for a remote backend (memory is server-side).
DEFAULT_REMOTE_MEMORY_MB = 0.0


class MemoryModel:
    """Megabyte footprint estimates per backend."""

    def __init__(self, local_mb: float = DEFAULT_LOCAL_MEMORY_MB,
                 remote_mb: float = DEFAULT_REMOTE_MEMORY_MB):
        if local_mb < 0 or remote_mb < 0:
            raise ValueError("memory defaults must be non-negative")
        self.local_mb = local_mb
        self.remote_mb = remote_mb

    def estimate_mb(self, backend: Backend) -> float:
        custom = getattr(backend, "estimated_memory_mb", None)
        if callable(custom):
            value = custom()
            if isinstance(value, (int, float)) and value >= 0:
                return float(value)
        declared = (backend.hardware_requirements() or {}).get("memory_mb")
        if isinstance(declared, (int, float)) and declared >= 0:
            return float(declared)
        return self.remote_mb if backend.is_remote else self.local_mb


class MemoryAwarePlanner(RungPlanner):
    """Wrap a planner; prune rungs that do not fit the memory budget.

    Memory is peak-per-rung, so pruning is per-rung (not cumulative):
    a rung survives iff its estimated footprint <= ``max_memory_mb``.
    With no budget set, every rung survives and is merely annotated.
    """

    def __init__(self, inner: RungPlanner, registry,
                 budget_mb: Optional[float] = None,
                 model: Optional[MemoryModel] = None):
        if budget_mb is not None and budget_mb < 0:
            raise ValueError(
                f"budget_mb must be non-negative, got {budget_mb}")
        self.inner = inner
        self.registry = registry
        self.budget_mb = budget_mb
        self.model = model or MemoryModel()

    def plan(self, ctx: RouterContext) -> RoutingPlan:
        plan = self.inner.plan(ctx)
        budget = (self.budget_mb if self.budget_mb is not None
                  else ctx.options.max_memory_mb)
        kept: List[RungNode] = []
        pruned: List[str] = []
        for node in plan.nodes:
            backend = self.registry.get(node.backend_name)
            mb = (self.model.estimate_mb(backend)
                  if backend is not None else 0.0)
            node.params["memory_estimate_mb"] = mb
            if budget is not None and mb > budget:
                pruned.append(
                    f"{node.backend_name}: est. {mb:.1f}MB > "
                    f"budget {budget:.1f}MB")
                continue
            kept.append(node)
        plan.nodes = kept
        plan.created_by = f"{plan.created_by}+memory"
        plan.rationale.append(
            f"memory: budget={budget}MB, pruned {len(pruned)}"
            + (": " + "; ".join(pruned) if pruned else ""))
        return plan
