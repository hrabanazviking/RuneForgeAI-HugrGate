"""Conditional routing DAGs. Slice 068.

A ladder is a line; some routing decisions are *graphs*. 
:class:`RoutingDAG` lets rungs branch on the request itself: each
:class:`DAGNode` carries a condition evaluated against the live request
at execution time, and edges say "if this node didn't win, these nodes
become eligible". :class:`DAGExecutor` walks the DAG in topological
order:

- a node runs only when its condition holds (else it is skipped, and its
  successors still become eligible — a false condition is not a failure);
- the first node to clear its gate wins and the DAG stops;
- below-gate results, abstentions, errors, and skips all release the
  node's successors (each successor runs once all its predecessors have
  settled);
- cycles are rejected by :meth:`RoutingDAG.validate` (Kahn's algorithm);
  the executor validates by default.

Conditions are declarative dicts so DAGs stay serializable (slices 070
and 072 build on this):

- ``{"always": True}``
- ``{"key_present": "ssn"}`` / ``{"key_absent": "ssn"}``
- ``{"spec_type": "categorical"}``
- ``{"qos": "priority"}`` / ``{"qos_in": ["priority", "critical"]}``
- ``{"min_state_keys": 2}``
- ``{"all": [...]}``, ``{"any": [...]}``, ``{"not": {...}}``

A raw callable ``(ctx) -> bool`` may be used instead; it is marked
non-serializable (``node.serializable`` is False) and replay/simulation
will refuse it rather than guess.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from typing import Any

from hugrgate.errors import Abstention, SpecError
from hugrgate.ladder import (
    RUNG_ACCEPTED,
    RUNG_BELOW_CONFIDENCE,
    RUNG_SKIPPED_UNKNOWN,
    LadderAuditEntry,
)
from hugrgate.routing.architecture import (
    LadderRouterV2,
    RouterContext,
    RoutingDecision,
    RoutingPlan,
    RungExecutor,
    RungNode,
)

__all__ = [
    "DAGExecutor",
    "DAGNode",
    "RoutingDAG",
    "evaluate_condition",
]

Condition = Any  # declarative dict or callable


def evaluate_condition(condition: Condition, ctx: RouterContext) -> bool:
    """Evaluate a declarative condition (or callable) against the request."""
    if callable(condition):
        return bool(condition(ctx))
    if not isinstance(condition, dict) or len(condition) != 1:
        raise SpecError(f"condition must be a single-key dict, got "
                        f"{condition!r}")
    (op, arg), = condition.items()
    if op == "always":
        return bool(arg)
    if op == "key_present":
        return str(arg) in ctx.state_keys
    if op == "key_absent":
        return str(arg) not in ctx.state_keys
    if op == "spec_type":
        return ctx.spec.type == arg
    if op == "qos":
        return ctx.options.qos == arg
    if op == "qos_in":
        return ctx.options.qos in arg
    if op == "min_state_keys":
        return ctx.state_size_hint >= int(arg)
    if op == "all":
        return all(evaluate_condition(c, ctx) for c in arg)
    if op == "any":
        return any(evaluate_condition(c, ctx) for c in arg)
    if op == "not":
        return not evaluate_condition(arg, ctx)
    raise SpecError(f"unknown condition operator: {op!r}")


class DAGNode:
    """One conditional rung of a routing DAG."""

    def __init__(self, name: str, backend_name: str,
                 min_confidence: float = 0.0,
                 latency_budget_ms: float | None = None,
                 condition: Condition = None):
        if not name:
            raise SpecError("DAG node needs a name")
        self.name = name
        self.rung = RungNode(backend_name, min_confidence,
                             latency_budget_ms,
                             why=f"DAG node {name}")
        self.condition = {"always": True} if condition is None else condition
        # validate the declarative form eagerly (callables skip this)
        if not callable(self.condition):
            evaluate_condition(self.condition,
                               _dummy_ctx())  # raises on bad shape

    @property
    def serializable(self) -> bool:
        return not callable(self.condition)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "rung": self.rung.to_dict(),
            "condition": (self.condition if self.serializable
                          else "<callable>"),
        }


def _dummy_ctx() -> RouterContext:
    from hugrgate.spec import DecisionSpec
    return RouterContext.from_request({}, DecisionSpec(
        type="categorical", options=["a", "b"]))


class RoutingDAG:
    """A validated directed acyclic graph of conditional rungs."""

    def __init__(self):
        self.nodes: dict[str, DAGNode] = {}
        self.edges: dict[str, list[str]] = {}

    def add_node(self, node: DAGNode) -> None:
        if node.name in self.nodes:
            raise SpecError(f"duplicate DAG node: {node.name!r}")
        self.nodes[node.name] = node
        self.edges.setdefault(node.name, [])

    def add_edge(self, frm: str, to: str) -> None:
        if frm not in self.nodes or to not in self.nodes:
            raise SpecError(
                f"DAG edge references unknown node: {frm!r} -> {to!r}")
        if frm == to:
            raise SpecError(f"DAG self-loop rejected: {frm!r}")
        if to not in self.edges[frm]:
            self.edges[frm].append(to)

    def roots(self) -> list[str]:
        targeted = {t for tos in self.edges.values() for t in tos}
        return [n for n in self.nodes if n not in targeted]

    def validate(self) -> list[str]:
        """Kahn's topological sort; raises SpecError on cycles."""
        in_degree = {n: 0 for n in self.nodes}
        for _, tos in self.edges.items():
            for to in tos:
                in_degree[to] += 1
        queue = deque(n for n, d in in_degree.items() if d == 0)
        order: list[str] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for nxt in self.edges[node]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)
        if len(order) != len(self.nodes):
            cyclic = sorted(set(self.nodes) - set(order))
            raise SpecError(f"DAG cycle involving: {cyclic}")
        if not self.nodes:
            raise SpecError("DAG has no nodes")
        return order

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": [n.to_dict() for n in self.nodes.values()],
                "edges": {k: list(v) for k, v in self.edges.items()}}


class DAGExecutor(RungExecutor):
    """Walk a :class:`RoutingDAG` in topological order.

    The DAG rides on the router (``router.dag``); ``plan`` is still built
    and recorded for audit continuity, but execution follows the DAG.
    """

    def __init__(self, dag: RoutingDAG | None = None,
                 validate: bool = True):
        self.dag = dag
        if dag is not None and validate:
            dag.validate()

    def execute(self, router: LadderRouterV2, plan: RoutingPlan,
                state: Mapping, ctx: RouterContext) -> RoutingDecision:
        dag = self.dag or getattr(router, "dag", None)
        if dag is None:
            raise SpecError("DAGExecutor needs a RoutingDAG "
                            "(executor or router.dag)")
        dag.validate()
        import time
        policy = ctx.policy
        started = time.perf_counter()
        audit: list[LadderAuditEntry] = []

        in_degree = {n: 0 for n in dag.nodes}
        for _, tos in dag.edges.items():
            for to in tos:
                in_degree[to] += 1
        ready: deque = deque(n for n, d in in_degree.items() if d == 0)
        settled: set[str] = set()
        topo_index = {name: i for i, name in enumerate(dag.validate())}

        def release(node_name: str) -> None:
            for nxt in dag.edges[node_name]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    ready.append(nxt)

        while ready:
            name = ready.popleft()
            if name in settled:
                continue
            settled.add(name)
            node = dag.nodes[name]
            i = topo_index[name]

            if not evaluate_condition(node.condition, ctx):
                audit.append(LadderAuditEntry(
                    i, node.rung.backend_name, RUNG_BELOW_CONFIDENCE,
                    detail=(f"DAG node {name!r}: condition "
                            f"{node.condition!r} false; skipping")))
                release(name)
                continue

            backend = router.registry.get(node.rung.backend_name)
            if backend is None:
                audit.append(LadderAuditEntry(
                    i, node.rung.backend_name, RUNG_SKIPPED_UNKNOWN,
                    detail="backend not in registry"))
                release(name)
                continue
            skip = router.skip_reason(backend, node.rung.to_ladder_rung(),
                                      ctx.spec, policy, started)
            if skip is not None:
                audit.append(LadderAuditEntry(
                    i, backend.name, skip[0], detail=skip[1]))
                release(name)
                continue

            result = router._attempt(backend, state, ctx.spec, None,
                                     audit, i)
            if result is None:
                release(name)
                continue
            router.note_availability(backend.name, True)
            router.note_cost(backend, result)
            router.note_energy(backend, result)
            gate = max(node.rung.min_confidence, policy.minimum_probability)
            if result.probability >= gate:
                audit[-1].outcome = RUNG_ACCEPTED
                audit[-1].detail = (f"DAG node {name!r}: probability "
                                    f"{result.probability:.3f} cleared gate "
                                    f"{gate:.3f}")
                router._log_attempt(state, ctx.spec, result, policy, gate)
                result.metadata["routing_plan"] = plan.to_dict()
                result.metadata["dag"] = dag.to_dict()
                result.metadata["ladder_trace"] = [e.to_dict()
                                                   for e in audit]
                result.metadata["ladder_rung"] = i
                result.metadata["ladder_backend"] = backend.name
                result.metadata["execution"] = "dag"
                result.metadata["dag_node"] = name
                router.last_audit = audit
                router.note_latencies(audit)
                return RoutingDecision(result=result, plan=plan,
                                       audit=[e.to_dict() for e in audit],
                                       accepted_rung=i)
            audit[-1].outcome = RUNG_BELOW_CONFIDENCE
            audit[-1].detail = (f"DAG node {name!r}: probability "
                                f"{result.probability:.3f} below gate "
                                f"{gate:.3f}; releasing successors")
            router._log_attempt(state, ctx.spec, result, policy, gate)
            release(name)

        router.last_audit = audit
        router.note_latencies(audit)
        raise Abstention(
            "DAG exhausted: no node cleared its gate",
            reason="ladder_exhausted",
            ladder_trace=[e.to_dict() for e in audit],
            plan_fingerprint=plan.fingerprint)
