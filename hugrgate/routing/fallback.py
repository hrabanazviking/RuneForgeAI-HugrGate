"""Fallback graph routing. Slice 067.

The linear ladder assumes "on failure, try the next rung". Reality is
richer: when backend A fails with a rate-limit error you want the
patient retry backend; when it fails with an auth error you want the
local fallback *now*. :class:`FallbackGraph` is a directed graph of
``(backend, error-kind) -> [fallback backends]`` edges consulted at run
time by :class:`FallbackGraphExecutor`:

- on a rung failure, edges matching the failure's error kind are
  followed *instead of* the linear plan order;
- a fallback rung inherits the failed node's gate and latency budget;
- error kinds are exception class names (``"BackendError"``,
  ``"BackendUnavailable"``, ...) or the ``"*"`` wildcard;
- cycles are rejected statically by :meth:`FallbackGraph.validate` and
  guarded dynamically by a per-request visited set — a fallback target
  already attempted is never retried.

Error-kind extraction reuses the audit entries :meth:`_attempt` writes:
``RUNG_UNAVAILABLE`` → ``BackendUnavailable``; ``RUNG_ERROR`` → the
exception class parsed from the detail (``"unexpected X: ..."``) or
``BackendError`` for plain backend errors; ``RUNG_ABSTAINED`` →
``Abstention`` (edges rarely match it, so abstentions still climb
linearly by default).
"""

from __future__ import annotations

import time
from collections import deque
from typing import Dict, List, Mapping, Optional, Set, Tuple

from hugrgate.errors import Abstention, SpecError
from hugrgate.ladder import (RUNG_ABSTAINED, RUNG_ACCEPTED,
                             RUNG_BELOW_CONFIDENCE, RUNG_ERROR,
                             RUNG_SKIPPED_UNKNOWN, RUNG_UNAVAILABLE,
                             LadderAuditEntry)
from hugrgate.routing.architecture import (LadderRouterV2, RouterContext,
                                            RungExecutor, RungNode,
                                            RoutingDecision, RoutingPlan)

__all__ = [
    "FallbackGraph",
    "FallbackGraphExecutor",
]

WILDCARD = "*"


class FallbackGraph:
    """Directed (backend, error-kind) -> fallback backends graph."""

    def __init__(self):
        self._edges: Dict[Tuple[str, str], List[str]] = {}

    def add_edge(self, from_backend: str, to_backend: str,
                 on: Tuple[str, ...] = ("BackendError",)) -> None:
        """On ``from_backend`` failing with one of ``on``, try ``to_backend``."""
        if from_backend == to_backend:
            raise SpecError(
                f"fallback self-loop rejected: {from_backend}")
        if not on:
            raise SpecError("fallback edge needs at least one error kind")
        for kind in on:
            self._edges.setdefault((from_backend, kind), [])
            if to_backend not in self._edges[(from_backend, kind)]:
                self._edges[(from_backend, kind)].append(to_backend)

    def fallbacks(self, backend_name: str,
                  error_kind: str) -> List[str]:
        """Fallback backends for this failure, specific edges first."""
        specific = self._edges.get((backend_name, error_kind), [])
        wildcard = self._edges.get((backend_name, WILDCARD), [])
        seen: Set[str] = set()
        ordered = []
        for name in specific + wildcard:
            if name not in seen:
                seen.add(name)
                ordered.append(name)
        return ordered

    def validate(self) -> None:
        """Raise SpecError if the graph contains a directed cycle."""
        adjacency: Dict[str, Set[str]] = {}
        for (frm, _kind), tos in self._edges.items():
            adjacency.setdefault(frm, set()).update(tos)
        visiting: Set[str] = set()
        done: Set[str] = set()

        def dfs(node: str, path: List[str]) -> None:
            if node in done:
                return
            if node in visiting:
                cycle = " -> ".join(path + [node])
                raise SpecError(f"fallback graph cycle: {cycle}")
            visiting.add(node)
            for nxt in adjacency.get(node, ()):
                dfs(nxt, path + [node])
            visiting.discard(node)
            done.add(node)

        for node in adjacency:
            dfs(node, [])

    def to_dict(self) -> Dict:
        return {f"{frm} [{kind}]": tos
                for (frm, kind), tos in self._edges.items()}


def _error_kinds(entry: LadderAuditEntry) -> Set[str]:
    if entry.outcome == RUNG_UNAVAILABLE:
        return {"BackendUnavailable"}
    if entry.outcome == RUNG_ABSTAINED:
        return {"Abstention"}
    if entry.outcome == RUNG_ERROR:
        detail = entry.detail
        if detail.startswith("unexpected "):
            return {detail[len("unexpected "):].split(":")[0]}
        return {"BackendError"}
    return set()


class FallbackGraphExecutor(RungExecutor):
    """Serial climb with graph-directed fallback on rung failures."""

    def __init__(self, graph: Optional[FallbackGraph] = None,
                 validate_graph: bool = True):
        self.graph = graph or FallbackGraph()
        if validate_graph:
            self.graph.validate()

    def execute(self, router: LadderRouterV2, plan: RoutingPlan,
                state: Mapping, ctx: RouterContext) -> RoutingDecision:
        policy = ctx.policy
        started = time.perf_counter()
        audit: List[LadderAuditEntry] = []

        # Worklist of (rung_index, node, via_fallback_of|None).
        worklist: deque = deque(
            (i, node, None) for i, node in enumerate(plan.nodes))
        visited: Set[str] = set()
        next_index = len(plan.nodes)  # fallback rungs get fresh indices

        nonlocal_next = [len(plan.nodes)]

        def attempt(i: int, node: RungNode, via: Optional[str]):
            backend = router.registry.get(node.backend_name)
            if backend is None:
                audit.append(LadderAuditEntry(
                    i, node.backend_name, RUNG_SKIPPED_UNKNOWN,
                    detail="backend not in registry"))
                return None
            skip = router.skip_reason(backend, node.to_ladder_rung(),
                                      ctx.spec, policy, started)
            if skip is not None:
                audit.append(LadderAuditEntry(
                    i, backend.name, skip[0], detail=skip[1]))
                return None
            visited.add(backend.name)
            result = router._attempt(backend, state, ctx.spec, None,
                                     audit, i)
            if result is None:
                kinds = _error_kinds(audit[-1])
                if via:
                    audit[-1].detail += f" [fallback for {via}]"
                for kind in sorted(kinds):
                    for target in self.graph.fallbacks(backend.name, kind):
                        if target in visited:
                            continue  # cycle guarded, silently
                        fb_node = RungNode(
                            target, node.min_confidence,
                            node.latency_budget_ms, node.mode,
                            why=(f"graph fallback for {backend.name} "
                                 f"on {kind}"),
                            params={"fallback_for": backend.name,
                                    "fallback_on": kind})
                        fb_index = nonlocal_next[0]
                        nonlocal_next[0] += 1
                        worklist.appendleft((fb_index, fb_node,
                                             backend.name))
                        audit.append(LadderAuditEntry(
                            fb_index, target, RUNG_BELOW_CONFIDENCE,
                            detail=(f"queued as graph fallback for "
                                    f"{backend.name} on {kind}")))
                return None
            router.note_availability(backend.name, True)
            router.note_cost(backend, result)
            router.note_energy(backend, result)
            gate = max(node.min_confidence, policy.minimum_probability)
            if result.probability >= gate:
                audit[-1].outcome = RUNG_ACCEPTED
                audit[-1].detail = (f"probability {result.probability:.3f} "
                                    f"cleared gate {gate:.3f}"
                                    + (f" [fallback for {via}]" if via
                                       else ""))
                router._log_attempt(state, ctx.spec, result, policy, gate)
                result.metadata["routing_plan"] = plan.to_dict()
                result.metadata["ladder_trace"] = [e.to_dict()
                                                   for e in audit]
                result.metadata["ladder_rung"] = i
                result.metadata["ladder_backend"] = backend.name
                result.metadata["execution"] = "fallback_graph"
                if via:
                    result.metadata["fallback_for"] = via
                router.last_audit = audit
                router.note_latencies(audit)
                return (node, backend, result, gate)
            audit[-1].outcome = RUNG_BELOW_CONFIDENCE
            audit[-1].detail = (f"probability {result.probability:.3f} "
                                f"below gate {gate:.3f}; climbing"
                                + (f" [fallback for {via}]" if via else ""))
            router._log_attempt(state, ctx.spec, result, policy, gate)
            return None

        while worklist:
            i, node, via = worklist.popleft()
            won = attempt(i, node, via)
            if won is not None:
                _node, _backend, result, _gate = won
                return RoutingDecision(result=result, plan=plan,
                                       audit=[e.to_dict() for e in audit],
                                       accepted_rung=i)

        router.last_audit = audit
        router.note_latencies(audit)
        raise Abstention(
            "fallback graph exhausted: no rung cleared its gate",
            reason="ladder_exhausted",
            ladder_trace=[e.to_dict() for e in audit],
            plan_fingerprint=plan.fingerprint)
