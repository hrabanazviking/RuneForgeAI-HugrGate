"""Contract inheritance — derive, specialize, and check compatibility.

Gjallarbrú slice 044.

Contracts are standalone: there is no way to say "a triage contract is
the base clinical contract with tighter bounds". This module adds:

- :func:`derive_contract`: build a child contract of the same kind from
  a base, overriding fields by name. Metadata deep-merges (child wins);
  the base's canonical hash is recorded as ``derived_from`` (provenance).
- :func:`is_compatible`: the Liskov check — is every value the child
  accepts also accepted by the base? Implemented per kind over the
  *value space* (what ``validate_value`` accepts), with conservative
  fallbacks where implication is undecidable.

Compatibility is about values, not matrices: a cost-sensitive child with
different prices but the same outcomes is compatible, because any label
it can decide is a label the base can decide.
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Any, Dict, List, Mapping, Optional, Tuple

from hugrgate.contracts.schema import (
    CONTRACT_KINDS,
    DecisionContract,
)
from hugrgate.errors import ContractError

__all__ = [
    "derive_contract",
    "is_compatible",
    "DERIVED_FROM_KEY",
]

#: Metadata key recording the base contract's canonical hash.
DERIVED_FROM_KEY = "derived_from"


def derive_contract(base: DecisionContract, contract_id: str, *,
                    name: str = "", description: str = "",
                    metadata: Optional[Dict[str, Any]] = None,
                    **overrides: Any) -> DecisionContract:
    """Derive a child contract from ``base``, overriding fields by name.

    The child has the base's kind; every non-metadata dataclass field is
    inherited unless overridden. Metadata merges (child keys win) and
    records ``derived_from: <base hash>``. Unknown override names raise
    ContractError instead of failing deep inside the dataclass.
    """
    if not isinstance(base, DecisionContract):
        raise ContractError(
            f"can only derive from a DecisionContract, got "
            f"{type(base).__name__}", code="bad_base_contract")
    if base.kind not in CONTRACT_KINDS:
        raise ContractError(f"base kind {base.kind!r} is not registered",
                            code="unknown_contract_kind")
    cls = type(base)
    try:
        field_names = [f.name for f in dataclasses.fields(base)
                       if not f.name.startswith("_")]
    except TypeError as e:
        raise ContractError(f"base {cls.__name__} is not a dataclass: {e}",
                            code="bad_base_contract")
    inheritable = [n for n in field_names
                   if n not in ("contract_id", "name", "description",
                                "metadata")]
    unknown = [k for k in overrides if k not in inheritable]
    if unknown:
        raise ContractError(
            f"unknown override field(s) for kind {base.kind!r}: {unknown}; "
            f"overridable: {inheritable}", code="bad_override")
    kwargs: Dict[str, Any] = {
        n: copy.deepcopy(getattr(base, n)) for n in inheritable
    }
    kwargs.update(overrides)
    merged = dict(base.metadata)
    merged.update(metadata or {})
    merged[DERIVED_FROM_KEY] = base.canonical_hash()
    try:
        return cls(contract_id=contract_id,
                   name=name or base.name,
                   description=description or base.description,
                   metadata=merged, **kwargs)
    except (TypeError, ContractError) as e:
        raise ContractError(f"cannot derive {base.kind!r} child: {e}",
                            code="derivation_failed") from None


# -- compatibility -----------------------------------------------------------

def _as_list(x: Any) -> List[str]:
    return list(x) if isinstance(x, (list, tuple)) else [x]


def _ordinal_ok(child: DecisionContract, base: DecisionContract) -> bool:
    order = [base.levels.index(l) for l in child.levels
             if l in base.levels]
    return (len(order) == len(child.levels)
            and all(b > a for a, b in zip(order, order[1:])))


def _numeric_interval_ok(child: DecisionContract, base: DecisionContract
                         ) -> bool:
    if not (base.minimum <= child.minimum
            and child.maximum <= base.maximum):
        return False
    if base.max_width is not None:
        if child.max_width is None or child.max_width > base.max_width:
            return False
    if base.min_confidence is not None:
        if (child.min_confidence is None
                or child.min_confidence < base.min_confidence):
            return False
    return True


def _multilabel_ok(child: DecisionContract, base: DecisionContract) -> bool:
    if not set(child.labels) <= set(base.labels):
        return False
    if base.exact_count != -1:
        if child.exact_count != base.exact_count:
            return False
    else:
        if child.exact_count != -1:
            if not (child.exact_count >= base.min_count
                    and (base.max_count == 0
                         or child.exact_count <= base.max_count)):
                return False
        else:
            if child.min_count < base.min_count:
                return False
            if base.max_count and (not child.max_count
                                   or child.max_count > base.max_count):
                return False
    if not set(base.required) <= set(child.required):
        return False
    if not set(base.forbidden) <= set(child.forbidden):
        return False
    for k, vs in base.implies.items():
        if k in child.labels:
            if not set(vs) <= set(child.implies.get(k, [])):
                return False
    base_ex = {(a, b) for a, vs in base.excludes.items() for b in vs}
    child_ex = {(a, b) for a, vs in child.excludes.items() for b in vs}
    return all((a, b) in child_ex or (b, a) in child_ex
               for a, b in base_ex if a in child.labels and b in child.labels)


def _outcomes_ok(child: DecisionContract, base: DecisionContract) -> bool:
    return set(child.outcomes) <= set(base.outcomes)


def _nested_ok(child: DecisionContract, base: DecisionContract) -> bool:
    # Accepted values are exactly the leaf paths.
    return set(child.leaf_paths()) <= set(base.leaf_paths())


def _hierarchy_ok(child: DecisionContract, base: DecisionContract) -> bool:
    # Value validity is label membership; structure may refine.
    return set(child.hierarchy.labels) <= set(base.hierarchy.labels)


def _composite_ok(child: DecisionContract, base: DecisionContract) -> bool:
    # Exact-keys semantics: same fields, each compatible.
    if set(child.fields) != set(base.fields):
        return False
    return all(_field_ok(child.fields[k], base.fields[k])
               for k in child.fields)


def _field_ok(child_f: Any, base_f: Any) -> bool:
    from hugrgate.spec import DecisionSpec
    if isinstance(child_f, DecisionContract) and isinstance(
            base_f, DecisionContract):
        return is_compatible(child_f, base_f)
    if isinstance(child_f, DecisionSpec) and isinstance(
            base_f, DecisionSpec):
        return _spec_ok(child_f, base_f)
    return False  # v1/v2 mix: conservative


def _spec_ok(child: Any, base: Any) -> bool:
    if child.type != base.type:
        return False
    space_c, space_b = child.value_space(), base.value_space()
    if child.type == "numeric":
        return (base.minimum <= child.minimum
                and child.maximum <= base.maximum)
    if child.type == "multilabel":
        return set(space_c) <= set(space_b)
    return set(space_c) <= set(space_b)


def _conditional_ok(child: DecisionContract, base: DecisionContract) -> bool:
    if not _composite_ok(child, base):
        return False
    # Conditions must agree exactly: any divergence changes which values
    # are accepted (missing vs. forbidden field values).
    return child.conditions == base.conditions


def _constrained_ok(child: DecisionContract, base: DecisionContract) -> bool:
    if not _composite_ok(child, base):
        return False
    # Conservative: every base constraint must appear among the child's
    # (list scan, not a set: targets may be unhashable dicts).
    return all(any(bc == cc for cc in child.constraints)
               for bc in base.constraints)


def _timed_ok(child: DecisionContract, base: DecisionContract) -> bool:
    if not _field_ok(child.inner, base.inner):
        return False
    if base.budget_ms is not None:
        if child.budget_ms is None or child.budget_ms > base.budget_ms:
            return False
    if base.not_before is not None:
        if child.not_before is None or child.not_before < base.not_before:
            return False
    if base.not_after is not None:
        if child.not_after is None or child.not_after > base.not_after:
            return False
    return True


_TYPE_SUBSUMES = {
    "any": {"string", "number", "integer", "boolean", "array", "object",
            "any"},
    "number": {"number", "integer"},
    "string": {"string"},
    "integer": {"integer"},
    "boolean": {"boolean"},
    "array": {"array"},
    "object": {"object"},
}


def _typed_mapping_ok(child: Any, base: Any, *, kind: str) -> bool:
    # A mapping valid under child must be valid under base.
    child_fields = {f.name: f for f in child.schema.fields} \
        if kind == "context" else {s.name: s for s in child.specs}
    base_fields = {f.name: f for f in base.schema.fields} \
        if kind == "context" else {s.name: s for s in base.specs}
    for name, bf in base_fields.items():
        cf = child_fields.get(name)
        if cf is None:
            # base requires/declares a field the child ignores
            if kind == "context":
                if bf.required:
                    return False
            else:
                if bf.required:
                    return False
            continue
        ctype = cf.type if kind == "context" else cf.dtype
        btype = bf.type if kind == "context" else bf.dtype
        # category dtype: child's categories must ⊆ base's
        if btype == "category" or ctype == "category":
            if ctype != "category" or btype != "category":
                return False
            if not set(cf.categories) <= set(bf.categories):
                return False
            continue
        if ctype not in _TYPE_SUBSUMES.get(btype, set()):
            return False
        if kind == "features":
            if bf.minimum is not None:
                if cf.minimum is None or cf.minimum < bf.minimum:
                    return False
            if bf.maximum is not None:
                if cf.maximum is None or cf.maximum > bf.maximum:
                    return False
    if child.allow_extra and not base.allow_extra:
        return False
    return True


def _explanation_ok(child: DecisionContract, base: DecisionContract) -> bool:
    if child.text_field != base.text_field:
        return False
    if child.reasons_field != base.reasons_field:
        return False
    if not set(base.required_fields) <= set(child.required_fields):
        return False
    if child.min_length < base.min_length:
        return False
    if child.min_reasons < base.min_reasons:
        return False
    if base.must_mention_value and not child.must_mention_value:
        return False
    return set(base.forbidden_phrases) <= set(child.forbidden_phrases)


_HANDLERS = {
    "ordinal": _ordinal_ok,
    "numeric-interval": _numeric_interval_ok,
    "multilabel-cardinality": _multilabel_ok,
    "distribution": _outcomes_ok,
    "cost-sensitive": _outcomes_ok,
    "utility": _outcomes_ok,
    "risk": _outcomes_ok,
    "nested-categorical": _nested_ok,
    "hierarchical-labels": _hierarchy_ok,
    "composite": _composite_ok,
    "conditional-composite": _conditional_ok,
    "constrained-composite": _constrained_ok,
    "timed": _timed_ok,
    "context-schema": lambda c, b: _typed_mapping_ok(c, b, kind="context"),
    "input-features": lambda c, b: _typed_mapping_ok(c, b, kind="features"),
    "explanation": _explanation_ok,
}


def is_compatible(child: DecisionContract, base: DecisionContract) -> bool:
    """True when every value ``child`` accepts, ``base`` also accepts.

    Kinds must match. Per-kind handlers encode value-space inclusion;
    unhandled kinds fall back to exact payload equality (conservative).
    Raises ContractError when either side is not a DecisionContract.
    """
    for obj, name in ((child, "child"), (base, "base")):
        if not isinstance(obj, DecisionContract):
            raise ContractError(f"{name} must be a DecisionContract, got "
                                f"{type(obj).__name__}",
                                code="bad_compatibility_arg")
    if child.kind != base.kind:
        return False
    handler = _HANDLERS.get(child.kind)
    if handler is None:
        # Conservative: only identical contracts are compatible.
        return child.to_dict() == base.to_dict()
    try:
        return bool(handler(child, base))
    except (ContractError, AttributeError, KeyError, ValueError):
        return False
