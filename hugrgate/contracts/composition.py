"""Contract composition — combining contracts. Gjallarbrú slice 045.

Inheritance (slice 044) is *is-a* specialization of one base. Composition
is *and*: merging, producting, and stacking contracts.

- :func:`merge`: union the fields of several composites of the *same*
  concrete sub-kind (``composite``, ``conditional-composite``,
  ``constrained-composite``). Field conflicts resolve by policy
  (``error`` | ``left`` | ``right``); conditions union; constraints
  concatenate. Cross-sub-kind merges are rejected — silently dropping
  conditions or constraints would lie about the result.
- :func:`product`: the joint decision — any two contracts as two named
  fields of one composite (``A x B``).
- :func:`with_deadline`: stack a temporal bound onto any contract via
  :class:`TimedContract`.

``derive_contract`` (044) is single-base override; ``merge`` is its
multi-base union sibling.
"""

from __future__ import annotations

from typing import Any

from hugrgate.contracts.composite import CompositeContract
from hugrgate.contracts.conditional import (
    ConditionalCompositeContract,
    FieldCondition,
)
from hugrgate.contracts.crossfield import (
    ConstrainedCompositeContract,
    FieldConstraint,
)
from hugrgate.contracts.deadlines import TimedContract
from hugrgate.contracts.schema import DecisionContract
from hugrgate.errors import ContractError
from hugrgate.spec import DecisionSpec

__all__ = [
    "MERGE_POLICIES",
    "merge",
    "product",
    "with_deadline",
]
#: Field-conflict policies for merge().
MERGE_POLICIES = ("error", "left", "right")


def _check_merge_inputs(
        contracts: tuple[CompositeContract, ...]) -> type:
    if len(contracts) < 2:
        raise ContractError("merge needs ≥2 contracts", code="bad_merge")
    for c in contracts:
        if not isinstance(c, CompositeContract):
            raise ContractError(
                f"merge needs CompositeContracts, got {type(c).__name__}",
                code="bad_merge")
    kinds = {type(c) for c in contracts}
    if len(kinds) != 1:
        names = sorted(c.kind for c in contracts)
        raise ContractError(
            f"merge needs one concrete composite sub-kind, got {names}; "
            f"merging conditional with constrained contracts would "
            f"silently drop rules", code="heterogeneous_merge")
    return kinds.pop()


def _resolve_conflict(name: str, existing: Any, incoming: Any,
                      policy: str) -> Any:
    if existing == incoming:
        return existing  # idempotent: identical fields merge quietly
    if policy == "error":
        raise ContractError(
            f"merge conflict on field {name!r}: {existing!r} vs {incoming!r}",
            code="merge_conflict", field=name)
    return existing if policy == "left" else incoming


def merge(*contracts: CompositeContract, contract_id: str,
          on_conflict: str = "error", name: str = "",
          description: str = "", metadata: dict[str, Any] | None = None,
          ) -> CompositeContract:
    """Union the fields of same-sub-kind composites.

    ``on_conflict``: ``"error"`` (default), ``"left"`` (first wins),
    ``"right"`` (last wins). Identical field definitions never conflict.
    """
    if on_conflict not in MERGE_POLICIES:
        raise ContractError(f"unknown merge policy {on_conflict!r}; "
                            f"policies: {list(MERGE_POLICIES)}",
                            code="bad_merge_policy")
    kind = _check_merge_inputs(contracts)
    fields: dict[str, Any] = {}
    for c in contracts:
        for fname, fcontract in c.fields.items():
            if fname in fields:
                fields[fname] = _resolve_conflict(
                    fname, fields[fname], fcontract, on_conflict)
            else:
                fields[fname] = fcontract
    kwargs: dict[str, Any] = {
        "contract_id": contract_id, "name": name,
        "description": description, "metadata": dict(metadata or {}),
        "fields": fields,
    }
    if kind is ConditionalCompositeContract:
        conditions: dict[str, FieldCondition] = {}
        for c in contracts:
            assert isinstance(c, ConditionalCompositeContract)
            for fname, cond in c.conditions.items():
                if fname in conditions:
                    conditions[fname] = _resolve_conflict(
                        f"condition:{fname}", conditions[fname], cond,
                        on_conflict)
                else:
                    conditions[fname] = cond
        kwargs["conditions"] = conditions
        return ConditionalCompositeContract(**kwargs)
    if kind is ConstrainedCompositeContract:
        constraints: list[FieldConstraint] = []
        for c in contracts:
            assert isinstance(c, ConstrainedCompositeContract)
            constraints.extend(c.constraints)
        kwargs["constraints"] = constraints
        return ConstrainedCompositeContract(**kwargs)
    return CompositeContract(**kwargs)


def product(a: DecisionContract, b: DecisionContract, *, contract_id: str,
            name_a: str = "first", name_b: str = "second", name: str = "",
            description: str = "",
            metadata: dict[str, Any] | None = None) -> CompositeContract:
    """The joint decision: ``a`` and ``b`` as two named composite fields."""
    for obj, label in ((a, "a"), (b, "b")):
        if not isinstance(obj, (DecisionContract, DecisionSpec)):
            raise ContractError(
                f"product argument {label} must be a DecisionContract or "
                f"DecisionSpec, got {type(obj).__name__}",
                code="bad_product_arg")
    if name_a == name_b:
        raise ContractError("product field names must differ",
                            code="bad_product_arg")
    for n in (name_a, name_b):
        if not isinstance(n, str) or not n:
            raise ContractError("product field names must be non-empty "
                                "strings", code="bad_product_arg")
    return CompositeContract(
        contract_id=contract_id, name=name, description=description,
        metadata=dict(metadata or {}),
        fields={name_a: a, name_b: b})


def with_deadline(contract: DecisionContract, *, contract_id: str,
                  budget_ms: float | None = None,
                  not_before: float | None = None,
                  not_after: float | None = None, name: str = "",
                  description: str = "",
                  metadata: dict[str, Any] | None = None) -> TimedContract:
    """Stack a temporal bound onto any contract (slice 040)."""
    if not isinstance(contract, (DecisionContract, DecisionSpec)):
        raise ContractError(
            f"with_deadline needs a DecisionContract or DecisionSpec, got "
            f"{type(contract).__name__}", code="bad_deadline_arg")
    return TimedContract(
        contract_id=contract_id, name=name, description=description,
        metadata=dict(metadata or {}), inner=contract,
        budget_ms=budget_ms, not_before=not_before, not_after=not_after)
