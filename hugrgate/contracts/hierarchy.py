"""Hierarchical labels — label forests with ancestor semantics.

Gjallarbrú slice 029.

Flat multilabel contracts treat ``"siamese"`` and ``"animal"`` as unrelated
strings. A hierarchical label contract organizes labels into a forest:
selecting ``"siamese"`` *implies* ``"cat"``, ``"mammal"``, ``"animal"``.
This module provides:

- :class:`LabelHierarchy`: an immutable label forest built from edges or a
  nested mapping, with ancestor/descendant queries, depth, lowest common
  ancestor, and ancestor closure;
- :class:`HierarchicalLabelContract` (kind ``"hierarchical-labels"``): a
  v2 contract whose values are label sets; validation requires every
  label to be known, and :meth:`close_value` expands a set with all
  implied ancestors;
- hierarchical precision/recall over ancestor-closed sets, so partial
  credit flows up the tree instead of all-or-nothing flat matching.

The forest is a true forest: every node has at most one parent, and
cycles are rejected at construction.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from typing import (
    Any,
    ClassVar,
)

from hugrgate.contracts.schema import (
    DecisionContract,
    register_kind,
)
from hugrgate.errors import ContractError

__all__ = [
    "HierarchicalLabelContract",
    "LabelHierarchy",
    "hierarchical_precision",
    "hierarchical_recall",
]


def _check_name(name: object, *, what: str = "label") -> str:
    if not isinstance(name, str) or not name:
        raise ContractError(f"{what} must be a non-empty string, "
                            f"got {name!r}", code="bad_label_name")
    return name


class LabelHierarchy:
    """An immutable forest of labels with ancestor semantics."""

    __slots__ = ("_children", "_depth", "_parent")

    def __init__(self, edges: Iterable[tuple[str, str]],
                 nodes: Iterable[str] = ()) -> None:
        parent: dict[str, str] = {}
        children: dict[str, list[str]] = {}
        for raw_p, raw_c in edges:
            p = _check_name(raw_p, what="parent label")
            c = _check_name(raw_c, what="child label")
            if p == c:
                raise ContractError(f"label {p!r} cannot be its own parent",
                                    code="self_parent")
            if c in parent:
                raise ContractError(
                    f"label {c!r} already has parent {parent[c]!r}; "
                    f"hierarchies are forests (one parent per label)",
                    code="multiple_parents")
            parent[c] = p
            children.setdefault(p, []).append(c)
            children.setdefault(c, [])
        for raw_n in nodes:
            children.setdefault(_check_name(raw_n, what="label"), [])
        self._detect_cycles(parent, children)
        self._parent = parent
        self._children = {k: tuple(v) for k, v in children.items()}
        self._depth = {n: self._compute_depth(n) for n in children}

    @staticmethod
    def _detect_cycles(parent: Mapping[str, str],
                       children: Mapping[str, list[str]]) -> None:
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in children}

        def visit(node: str, stack: list[str]) -> None:
            color[node] = GRAY
            for nxt in children.get(node, []):
                if color[nxt] == GRAY:
                    cycle = " -> ".join([*stack, node, nxt])
                    raise ContractError(
                        f"label hierarchy contains a cycle: {cycle}",
                        code="label_cycle")
                if color[nxt] == WHITE:
                    visit(nxt, [*stack, node])
            color[node] = BLACK

        for node in sorted(children):
            if color[node] == WHITE:
                visit(node, [])

    def _compute_depth(self, node: str) -> int:
        d, cur = 0, node
        while cur in self._parent:
            cur = self._parent[cur]
            d += 1
        return d

    # -- constructors ------------------------------------------------------

    @classmethod
    def from_edges(cls, edges: Iterable[tuple[str, str]],
                   nodes: Iterable[str] = ()) -> LabelHierarchy:
        """Build from ``(parent, child)`` pairs plus isolated ``nodes``."""
        return cls(list(edges), nodes)

    @classmethod
    def from_nested(cls, nested: Mapping[str, Any]) -> LabelHierarchy:
        """Build from a nested mapping: ``{"a": {"b": {"c": {}}}}``."""
        edges: list[tuple[str, str]] = []
        seen: list[str] = []

        def walk(sub: Mapping[str, Any], parent: str | None) -> None:
            for key, kids in sub.items():
                name = _check_name(key)
                seen.append(name)
                if parent is not None:
                    edges.append((parent, name))
                if isinstance(kids, Mapping):
                    walk(kids, name)
                elif kids:
                    raise ContractError(
                        "nested hierarchy values must be mappings, "
                        f"got {kids!r} under {name!r}",
                        code="bad_nested_hierarchy")

        if not isinstance(nested, Mapping):
            raise ContractError("nested hierarchy must be a mapping",
                                code="bad_nested_hierarchy")
        walk(nested, None)
        return cls(edges, seen)

    # -- queries -------------------------------------------------------------

    def __contains__(self, label: object) -> bool:
        return isinstance(label, str) and label in self._children

    def __len__(self) -> int:
        return len(self._children)

    @property
    def labels(self) -> frozenset[str]:
        """Every label in the forest."""
        return frozenset(self._children)

    @property
    def roots(self) -> tuple[str, ...]:
        """Labels with no parent, in sorted order."""
        return tuple(sorted(n for n in self._children
                            if n not in self._parent))

    @property
    def leaves(self) -> tuple[str, ...]:
        """Labels with no children, in sorted order."""
        return tuple(sorted(n for n, ch in self._children.items() if not ch))

    def parent_of(self, label: str) -> str | None:
        """The parent of ``label``, or None for roots."""
        _check_name(label)
        if label not in self._children:
            raise ContractError(f"unknown label: {label!r}",
                                code="unknown_label")
        return self._parent.get(label)

    def children_of(self, label: str) -> tuple[str, ...]:
        """Direct children of ``label``."""
        _check_name(label)
        if label not in self._children:
            raise ContractError(f"unknown label: {label!r}",
                                code="unknown_label")
        return self._children[label]

    def ancestors(self, label: str) -> tuple[str, ...]:
        """Ancestors from the root down to the parent."""
        _check_name(label)
        if label not in self._children:
            raise ContractError(f"unknown label: {label!r}",
                                code="unknown_label")
        chain: list[str] = []
        cur = self._parent.get(label)
        while cur is not None:
            chain.append(cur)
            cur = self._parent.get(cur)
        return tuple(reversed(chain))

    def descendants(self, label: str) -> frozenset[str]:
        """All labels strictly below ``label``."""
        _check_name(label)
        if label not in self._children:
            raise ContractError(f"unknown label: {label!r}",
                                code="unknown_label")
        out: set[str] = set()
        stack = list(self._children[label])
        while stack:
            node = stack.pop()
            if node not in out:
                out.add(node)
                stack.extend(self._children[node])
        return frozenset(out)

    def depth_of(self, label: str) -> int:
        """Edges from the root to ``label`` (roots = 0)."""
        _check_name(label)
        if label not in self._children:
            raise ContractError(f"unknown label: {label!r}",
                                code="unknown_label")
        return self._depth[label]

    def lowest_common_ancestor(self, a: str, b: str) -> str | None:
        """Deepest label that is an ancestor of (or equal to) both."""
        for label in (a, b):
            _check_name(label)
            if label not in self._children:
                raise ContractError(f"unknown label: {label!r}",
                                    code="unknown_label")
        a_chain = (a, *tuple(reversed(self.ancestors(a))))
        b_set = frozenset((b, *tuple(reversed(self.ancestors(b)))))
        for node in a_chain:
            if node in b_set:
                return node
        return None

    def close(self, labels: Iterable[str]) -> frozenset[str]:
        """Ancestor closure: ``labels`` plus every implied ancestor."""
        out: set[str] = set()
        for label in labels:
            _check_name(label)
            if label not in self._children:
                raise ContractError(f"unknown label: {label!r}",
                                    code="unknown_label")
            out.add(label)
            out.update(self.ancestors(label))
        return frozenset(out)

    def edges(self) -> list[tuple[str, str]]:
        """The ``(parent, child)`` edge list, sorted."""
        return sorted((p, c) for c, p in self._parent.items())


def hierarchical_precision(predicted: Collection[str],
                           truth: Collection[str],
                           hierarchy: LabelHierarchy) -> float:
    """``|close(P) ∩ close(T)| / |close(P)|`` — 1.0 for empty prediction."""
    p_closed = hierarchy.close(predicted)
    if not p_closed:
        return 1.0
    return len(p_closed & hierarchy.close(truth)) / len(p_closed)


def hierarchical_recall(predicted: Collection[str],
                        truth: Collection[str],
                        hierarchy: LabelHierarchy) -> float:
    """``|close(P) ∩ close(T)| / |close(T)|`` — 1.0 for empty truth."""
    t_closed = hierarchy.close(truth)
    if not t_closed:
        return 1.0
    return len(hierarchy.close(predicted) & t_closed) / len(t_closed)


@register_kind
@dataclass
class HierarchicalLabelContract(DecisionContract):
    """A multilabel contract over a label forest (kind ``"hierarchical-labels"``).

    Values are collections of labels; every label must be known to the
    hierarchy. :meth:`close_value` expands a prediction with implied
    ancestors for hierarchy-aware scoring.
    """

    kind: ClassVar[str] = "hierarchical-labels"

    edges: list[tuple[str, str]] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)  # isolated roots
    _hierarchy: LabelHierarchy = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.edges, list):
            raise ContractError("'edges' must be a list of (parent, child) "
                                "pairs", code="bad_edges")
        clean: list[tuple[str, str]] = []
        for e in self.edges:
            if (not isinstance(e, (list, tuple)) or len(e) != 2):
                raise ContractError(f"edge must be a (parent, child) pair, "
                                    f"got {e!r}", code="bad_edge")
            clean.append((e[0], e[1]))
        self.edges = clean
        if not isinstance(self.labels, list):
            raise ContractError("'labels' must be a list of label names",
                                code="bad_labels")
        clean_labels = [_check_name(lbl) for lbl in self.labels]
        if len(set(clean_labels)) != len(clean_labels):
            raise ContractError("isolated labels must be unique",
                                code="duplicate_labels")
        self.labels = clean_labels
        try:
            hierarchy = LabelHierarchy.from_edges(clean, clean_labels)
        except ContractError as e:
            raise ContractError(f"invalid label hierarchy: {e.message}",
                                code=e.details.get("code", "bad_hierarchy")) from e
        if not len(hierarchy):
            raise ContractError("hierarchical label contract needs ≥1 label",
                                code="empty_hierarchy")
        self._hierarchy = hierarchy

    @property
    def hierarchy(self) -> LabelHierarchy:
        """The label forest (rebuilt on deserialization)."""
        return self._hierarchy

    def _check_labels(self, value: Any) -> list[str]:
        if isinstance(value, str) or not isinstance(value, Collection):
            raise ContractError(
                "hierarchical label value must be a collection of labels, "
                f"got {type(value).__name__}", code="bad_value_type")
        labels = list(value)
        for label in labels:
            _check_name(label)
            if label not in self.hierarchy:
                raise ContractError(f"unknown label: {label!r}",
                                    code="unknown_label")
        if len(set(labels)) != len(labels):
            raise ContractError(f"duplicate labels in value: {labels}",
                                code="duplicate_labels")
        return labels

    def validate_value(self, value: Any) -> None:
        self._check_labels(value)

    def close_value(self, value: Collection[str]) -> frozenset[str]:
        """The value's ancestor closure — every implied ancestor included."""
        return self.hierarchy.close(self._check_labels(value))

    def _payload_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"edges": [[p, c] for p, c in self.edges]}
        if self.labels:
            d["labels"] = list(self.labels)
        return d

    @classmethod
    def _from_payload(cls, d: Mapping[str, Any],
                      common: dict[str, Any]) -> HierarchicalLabelContract:
        edges = d.get("edges")
        if not isinstance(edges, list):
            raise ContractError("hierarchical label payload needs an "
                                "'edges' list", code="missing_edges")
        labels = d.get("labels", [])
        if not isinstance(labels, list):
            raise ContractError("'labels' must be a list", code="bad_labels")
        return cls(edges=[tuple(e) for e in edges], labels=list(labels),
                   **common)

    def describe(self) -> str:
        h = self.hierarchy
        return (f"hierarchical-labels contract {self.name or self.contract_id!r}: "
                f"{len(h)} labels, {len(h.roots)} roots, "
                f"{len(h.leaves)} leaves")
