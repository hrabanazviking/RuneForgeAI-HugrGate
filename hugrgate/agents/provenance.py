"""Agent Nervous System (Campaign XVI) — agent provenance graph.

Slice 396.  Every nervous-system decision — routed intent,
dispatched fan-out, fused vote, escalated ticket, gated memory
access, human verdict — should leave a traceable lineage.
:class:`AgentProvenanceGraph` is that lineage: a DAG of decision
nodes.

- :meth:`add_decision` records a node (``kind``: ``"route"``,
  ``"dispatch"``, ``"fuse"``, ``"escalate"``, ``"tool_call"``,
  ``"review"``, ``"gate"``, ...) with ``agent_id``,
  ``ticket_id``, and parent node ids; parents must already
  exist and node ids must be new — the graph is acyclic *by
  construction*, and :meth:`check_acyclic` verifies it for the
  release gate (400);
- :meth:`ancestors` / :meth:`descendants` walk the DAG;
  :meth:`lineage` returns every root-to-node path (why did this
  decision happen?);
- :meth:`export` serializes nodes + edges in topological order
  — plain dicts/lists, wire-safe for the replay slice (397).

This complements :mod:`hugrgate.provenance` (decision
provenance) rather than replacing it: that module tracks *what
a decision was*; this graph tracks *which agent decisions led
to which* across the nervous system.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "AgentProvenanceGraph",
    "ProvenanceNode",
]

#: Known decision kinds (open-ended: custom kinds allowed).
KINDS: tuple[str, ...] = (
    "route", "dispatch", "fuse", "escalate", "tool_call", "review",
    "gate", "notify", "budget", "loop", "runaway",
)


@dataclass(frozen=True)
class ProvenanceNode:
    """One decision in the lineage DAG."""

    node_id: str
    kind: str
    agent_id: str
    ticket_id: str
    parents: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("node_id must be non-empty")
        if not self.kind:
            raise ValueError("kind must be non-empty")


class AgentProvenanceGraph:
    """DAG of agent decisions with lineage queries."""

    def __init__(self) -> None:
        self._nodes: dict[str, ProvenanceNode] = {}
        self._children: dict[str, list[str]] = {}

    def add_decision(
        self,
        node_id: str,
        *,
        kind: str,
        agent_id: str,
        ticket_id: str,
        parents: tuple[str, ...] | list[str] = (),
        details: dict[str, Any] | None = None,
    ) -> ProvenanceNode:
        """Record a decision node; parents must already exist."""
        if node_id in self._nodes:
            raise ValueError(f"duplicate node {node_id!r}")
        parents = tuple(parents)
        for p in parents:
            if p not in self._nodes:
                raise ValueError(f"unknown parent node {p!r}")
            if p == node_id:
                raise ValueError("node cannot be its own parent")
        node = ProvenanceNode(
            node_id=node_id, kind=kind, agent_id=agent_id,
            ticket_id=ticket_id, parents=parents,
            details=dict(details or {}),
        )
        self._nodes[node_id] = node
        for p in parents:
            self._children.setdefault(p, []).append(node_id)
        self._children.setdefault(node_id, [])
        return node

    def get(self, node_id: str) -> ProvenanceNode | None:
        """The node, or None when unknown."""
        return self._nodes.get(node_id)

    def roots(self) -> tuple[str, ...]:
        """Node ids with no parents, sorted."""
        return tuple(sorted(n.node_id for n in self._nodes.values()
                            if not n.parents))

    def ancestors(self, node_id: str) -> tuple[str, ...]:
        """All ancestors of ``node_id`` (sorted, excluding itself)."""
        if node_id not in self._nodes:
            raise ValueError(f"unknown node {node_id!r}")
        seen: set[str] = set()
        stack = list(self._nodes[node_id].parents)
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(self._nodes[cur].parents)
        return tuple(sorted(seen))

    def descendants(self, node_id: str) -> tuple[str, ...]:
        """All descendants of ``node_id`` (sorted, excluding itself)."""
        if node_id not in self._nodes:
            raise ValueError(f"unknown node {node_id!r}")
        seen: set[str] = set()
        stack = list(self._children[node_id])
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(self._children[cur])
        return tuple(sorted(seen))

    def lineage(self, node_id: str) -> tuple[tuple[str, ...], ...]:
        """Every root-to-``node_id`` path (why did this happen?)."""
        if node_id not in self._nodes:
            raise ValueError(f"unknown node {node_id!r}")
        paths: list[tuple[str, ...]] = []

        def walk(cur: str, path: tuple[str, ...]) -> None:
            node = self._nodes[cur]
            path = (cur, *path)
            if not node.parents:
                paths.append(path)
            for p in node.parents:
                walk(p, path)

        walk(node_id, ())
        return tuple(sorted(paths))

    def check_acyclic(self) -> bool:
        """True when the graph is a DAG (Kahn's algorithm)."""
        indegree = {nid: len(n.parents) for nid, n in self._nodes.items()}
        queue: deque[str] = deque(
            nid for nid, deg in indegree.items() if deg == 0)
        visited = 0
        while queue:
            cur = queue.popleft()
            visited += 1
            for child in self._children[cur]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        return visited == len(self._nodes)

    def export(self) -> dict[str, Any]:
        """Wire-safe export: nodes in topological order + edges."""
        indegree = {nid: len(n.parents) for nid, n in self._nodes.items()}
        queue: deque[str] = deque(
            sorted(nid for nid, deg in indegree.items() if deg == 0))
        order: list[str] = []
        while queue:
            cur = queue.popleft()
            order.append(cur)
            for child in sorted(self._children[cur]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        return {
            "nodes": [
                {
                    "node_id": n.node_id, "kind": n.kind,
                    "agent_id": n.agent_id, "ticket_id": n.ticket_id,
                    "parents": list(n.parents), "details": dict(n.details),
                }
                for nid in order for n in [self._nodes[nid]]
            ],
            "edges": [
                [p, nid] for nid in order
                for p in self._nodes[nid].parents
            ],
        }

    def __len__(self) -> int:
        return len(self._nodes)
