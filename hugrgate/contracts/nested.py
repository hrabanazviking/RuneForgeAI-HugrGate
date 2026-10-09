"""Nested categorical contracts — decision trees. Gjallarbrú slice 028.

A flat categorical contract picks one of N options. A nested categorical
contract picks an option, and that option may refine into another nested
categorical contract: ``("animal", "mammal", "dog")``. Values are paths —
tuples of strings or dotted strings (``"animal.mammal.dog"``) — validated
by walking the tree. A valid decision is always a root-to-leaf path.

Invariants: options are unique non-empty dot-free strings; child keys are
a subset of options; every child is itself a nested categorical contract;
nesting depth is bounded (:data:`MAX_NESTING_DEPTH`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

from hugrgate.contracts.schema import (
    DecisionContract,
    contract_from_dict,
    register_kind,
)
from hugrgate.errors import ContractError

__all__ = [
    "MAX_NESTING_DEPTH",
    "NestedCategoricalContract",
    "parse_path",
]

#: Hard bound on nesting depth (root alone = 1).
MAX_NESTING_DEPTH = 8


def parse_path(value: Any) -> tuple[str, ...]:
    """Normalize a decision path to a tuple of non-empty strings."""
    if isinstance(value, str):
        parts = tuple(value.split("."))
    elif isinstance(value, (list, tuple)):
        parts = tuple(value)
    else:
        raise ContractError(
            f"nested categorical value must be a dotted string or a "
            f"sequence of strings, got {type(value).__name__}",
            code="bad_path_type")
    if not parts or any(not isinstance(p, str) or not p for p in parts):
        raise ContractError(
            f"nested categorical path needs ≥1 non-empty string segment: "
            f"{value!r}",
            code="bad_path_segments")
    return parts


@register_kind
@dataclass
class NestedCategoricalContract(DecisionContract):
    """A categorical decision tree: options refining into sub-decisions."""

    kind: ClassVar[str] = "nested-categorical"

    options: list[str] = field(default_factory=list)
    children: dict[str, NestedCategoricalContract] = field(
        default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.options:
            raise ContractError("nested categorical needs ≥1 option",
                                code="no_options")
        if len(set(self.options)) != len(self.options):
            raise ContractError("nested categorical options must be unique",
                                code="duplicate_options")
        if any(not isinstance(o, str) or not o or "." in o
               for o in self.options):
            raise ContractError(
                "nested categorical options must be non-empty strings "
                "without dots (dots separate path segments)",
                code="bad_option")
        if not isinstance(self.children, dict):
            raise ContractError("children must be a dict",
                                code="bad_children")
        unknown = [k for k in self.children if k not in self.options]
        if unknown:
            raise ContractError(
                f"children keys must be options, unknown: {unknown}",
                code="child_not_an_option")
        for key, child in self.children.items():
            if not isinstance(child, NestedCategoricalContract):
                raise ContractError(
                    f"child {key!r} must be a NestedCategoricalContract",
                    code="bad_child_type")
        if self.depth() > MAX_NESTING_DEPTH:
            raise ContractError(
                f"nesting depth {self.depth()} exceeds max "
                f"{MAX_NESTING_DEPTH}",
                code="nesting_too_deep")

    # -- structure ---------------------------------------------------------

    def depth(self) -> int:
        """Longest root-to-leaf path length (root alone = 1)."""
        if not self.children:
            return 1
        return 1 + max(c.depth() for c in self.children.values())

    def leaf_paths(self) -> list[tuple[str, ...]]:
        """Every root-to-leaf path in the tree, in option order."""
        paths: list[tuple[str, ...]] = []
        for opt in self.options:
            child = self.children.get(opt)
            if child is None:
                paths.append((opt,))
            else:
                paths.extend((opt, *rest) for rest in child.leaf_paths())
        return paths

    def is_leaf(self, option: str) -> bool:
        """True when ``option`` has no refining child contract."""
        return option in self.options and option not in self.children

    def subcontract_at(self, path: Sequence[str]) -> NestedCategoricalContract:
        """The subtree contract rooted at ``path`` (path may end at a leaf)."""
        parts = parse_path(path)
        node = self
        for part in parts:
            child = node.children.get(part)
            if child is None:
                raise ContractError(
                    f"no subtree at {list(parts)!r}: {part!r} "
                    f"has no child contract",
                    code="no_subtree_at_path")
            node = child
        return node

    # -- validation ----------------------------------------------------------

    def validate_value(self, value: Any) -> None:
        parts = parse_path(value)
        node = self
        for i, part in enumerate(parts):
            if part not in node.options:
                raise ContractError(
                    f"unknown option {part!r} at depth {i}; "
                    f"options here: {node.options}",
                    code="unknown_option")
            child = node.children.get(part)
            if child is None:
                if i != len(parts) - 1:
                    raise ContractError(
                        f"{part!r} is a leaf; trailing segments "
                        f"{list(parts[i + 1:])!r} are invalid",
                        code="trailing_segments_at_leaf")
                return
            node = child
        raise ContractError(
            f"path {list(parts)!r} ends at branch option "
            f"{parts[-1]!r}; refine into {list(node.options)!r}",
            code="path_ends_at_branch")

    # -- serialization ---------------------------------------------------------

    def _payload_dict(self) -> dict[str, Any]:
        return {
            "options": list(self.options),
            "children": {k: v.to_dict() for k, v in self.children.items()},
        }

    @classmethod
    def _from_payload(cls, d: Mapping[str, Any],
                      common: dict[str, Any]) -> NestedCategoricalContract:
        options = d.get("options")
        if not isinstance(options, list):
            raise ContractError("nested categorical payload needs an "
                                "'options' list", code="missing_options")
        raw_children = d.get("children", {})
        if not isinstance(raw_children, dict):
            raise ContractError("'children' must be a dict",
                                code="bad_children")
        children = {}
        for k, v in raw_children.items():
            child = contract_from_dict(v)
            if not isinstance(child, NestedCategoricalContract):
                raise ContractError(
                    f"child {k!r} is kind {child.kind!r}, must be "
                    f"'nested-categorical'",
                    code="bad_child_kind")
            children[k] = child
        return cls(options=options, children=children, **common)

    def describe(self) -> str:
        return (f"nested-categorical contract {self.name or self.contract_id!r}: "
                f"{len(self.options)} options, "
                f"{len(self.leaf_paths())} leaf paths, "
                f"depth {self.depth()}")
