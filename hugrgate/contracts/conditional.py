"""Conditional decision fields. Gjallarbrú slice 031.

A composite contract (slice 030) requires every field, always. Real
decisions are conditional: ``allergy_details`` only matters when
``has_allergy`` is true; ``dosage`` only when ``medication`` is not
``"none"``.

:class:`ConditionalCompositeContract` (kind ``"conditional-composite"``)
extends :class:`CompositeContract` with per-field
:class:`FieldCondition`s. Given a value mapping, activation is computed
to a fixpoint — conditions may chain (a field conditional on another
conditional field cascades). Only active fields are required and
validated; providing a value for an *inactive* field is rejected as a
contradiction. Condition cycles and self-references are rejected at
construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Mapping, Set

from hugrgate.contracts.composite import (
    CompositeContract,
    FieldContract,
    _validate_spec_value,
)
from hugrgate.contracts.schema import DecisionContract, register_kind
from hugrgate.errors import ContractError

__all__ = [
    "CONDITION_OPS",
    "FieldCondition",
    "ConditionalCompositeContract",
]

#: Supported condition operators.
CONDITION_OPS = ("eq", "ne", "in", "not_in", "gt", "ge", "lt", "le")


@dataclass(frozen=True)
class FieldCondition:
    """``field`` is active iff ``value[on_field] <op> expected``."""

    on_field: str
    op: str
    expected: Any = None

    def __post_init__(self) -> None:
        if not isinstance(self.on_field, str) or not self.on_field:
            raise ContractError("condition on_field must be a non-empty "
                                "string", code="bad_condition_field")
        if self.op not in CONDITION_OPS:
            raise ContractError(
                f"unknown condition op {self.op!r}; ops: {list(CONDITION_OPS)}",
                code="bad_condition_op")
        if self.op in ("in", "not_in"):
            if isinstance(self.expected, str) or not isinstance(
                    self.expected, (list, tuple, set, frozenset)):
                raise ContractError(
                    f"op {self.op!r} needs a collection of candidates",
                    code="bad_condition_expected")

    def satisfied_by(self, field_value: Any) -> bool:
        """Evaluate the condition against one already-decided field value."""
        try:
            if self.op == "eq":
                return bool(field_value == self.expected)
            if self.op == "ne":
                return bool(field_value != self.expected)
            if self.op == "in":
                return field_value in self.expected
            if self.op == "not_in":
                return field_value not in self.expected
            if self.op == "gt":
                return bool(field_value > self.expected)
            if self.op == "ge":
                return bool(field_value >= self.expected)
            if self.op == "lt":
                return bool(field_value < self.expected)
            return bool(field_value <= self.expected)  # le
        except TypeError as e:
            raise ContractError(
                f"condition {self.op!r} cannot compare "
                f"{field_value!r} with {self.expected!r}: {e}",
                code="condition_type_mismatch") from None

    def to_dict(self) -> Dict[str, Any]:
        expected = self.expected
        if isinstance(expected, (set, frozenset)):
            expected = sorted(expected)
        return {"on_field": self.on_field, "op": self.op,
                "expected": expected}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "FieldCondition":
        if not isinstance(d, Mapping):
            raise ContractError("condition must be a mapping",
                                code="bad_condition")
        try:
            return cls(on_field=d["on_field"], op=d["op"],
                       expected=d.get("expected"))
        except KeyError as e:
            raise ContractError(f"condition missing key: {e}",
                                code="bad_condition") from None


@register_kind
@dataclass
class ConditionalCompositeContract(CompositeContract):
    """A composite whose fields activate conditionally (kind
    ``"conditional-composite"``)."""

    kind: ClassVar[str] = "conditional-composite"

    conditions: Dict[str, FieldCondition] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.conditions, dict):
            raise ContractError("'conditions' must be a dict",
                                code="bad_conditions")
        for name, cond in self.conditions.items():
            if name not in self.fields:
                raise ContractError(
                    f"condition targets unknown field {name!r}",
                    code="condition_on_unknown_field")
            if not isinstance(cond, FieldCondition):
                raise ContractError(
                    f"condition for {name!r} must be a FieldCondition",
                    code="bad_condition")
            if cond.on_field not in self.fields:
                raise ContractError(
                    f"condition for {name!r} references unknown field "
                    f"{cond.on_field!r}", code="condition_ref_unknown_field")
            if cond.on_field == name:
                raise ContractError(
                    f"condition for {name!r} cannot reference itself",
                    code="condition_self_reference")
        self._check_condition_cycles()

    def _check_condition_cycles(self) -> None:
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in self.fields}

        def visit(node: str, stack: List[str]) -> None:
            color[node] = GRAY
            cond = self.conditions.get(node)
            if cond is not None:
                nxt = cond.on_field
                if color[nxt] == GRAY:
                    raise ContractError(
                        "condition cycle: " + " -> ".join(stack + [node, nxt]),
                        code="condition_cycle")
                if color[nxt] == WHITE:
                    visit(nxt, stack + [node])
            color[node] = BLACK

        for name in self.fields:
            if color[name] == WHITE:
                visit(name, [])

    # -- activation --------------------------------------------------------

    def active_fields(self, value: Mapping[str, Any]) -> List[str]:
        """Field names active under a (possibly partial) value mapping.

        A conditional field is active iff its referenced field is present
        in ``value`` and the condition holds; activation cascades through
        chains of conditional fields to a fixpoint.
        """
        active: Set[str] = {n for n in self.fields
                            if n not in self.conditions}
        changed = True
        while changed:
            changed = False
            for name, cond in self.conditions.items():
                if name in active or cond.on_field not in value:
                    continue
                if cond.satisfied_by(value[cond.on_field]):
                    active.add(name)
                    changed = True
        return [n for n in self.fields if n in active]

    def activation_report(self, value: Mapping[str, Any]) -> Dict[str, bool]:
        """``{field: is_active}`` for every field — explanation support."""
        active = set(self.active_fields(value))
        return {n: (n in active) for n in self.fields}

    # -- validation ----------------------------------------------------------

    def validate_value(self, value: Any) -> None:
        if isinstance(value, str) or not isinstance(value, Mapping):
            raise ContractError(
                "composite value must be a mapping of field -> value, "
                f"got {type(value).__name__}", code="composite_not_mapping")
        unknown = [k for k in value if k not in self.fields]
        if unknown:
            raise ContractError(
                f"composite value has undeclared fields: {unknown}",
                code="unknown_fields", unknown=unknown)
        # Validate unconditional fields first: conditions read them.
        for name in self.fields:
            if name in self.conditions or name not in value:
                continue
            self._validate_field(name, value[name])
        active = set(self.active_fields(value))
        missing = [n for n in self.fields
                   if n in active and n not in value]
        if missing:
            raise ContractError(
                f"conditional composite missing active fields: {missing}",
                code="missing_fields", missing=missing)
        inactive_provided = [k for k in value if k not in active]
        if inactive_provided:
            raise ContractError(
                f"values provided for inactive fields: {inactive_provided}",
                code="inactive_field_provided",
                fields=inactive_provided)
        for name in self.fields:
            if name in self.conditions and name in value:
                self._validate_field(name, value[name])

    def _validate_field(self, name: str, field_value: Any) -> None:
        sub: FieldContract = self.fields[name]
        try:
            if isinstance(sub, DecisionContract):
                sub.validate_value(field_value)
            else:
                _validate_spec_value(sub, field_value, field_name=name)
        except ContractError as e:
            raise ContractError(
                f"field {name!r}: {e.message}",
                code=e.details.get("code", "field_invalid"),
                field=name) from None

    # -- serialization ---------------------------------------------------------

    def _payload_dict(self) -> Dict[str, Any]:
        d = super()._payload_dict()
        if self.conditions:
            d["conditions"] = {n: c.to_dict()
                               for n, c in self.conditions.items()}
        return d

    @classmethod
    def _from_payload(cls, d: Mapping[str, Any],
                      common: Dict[str, Any]) -> "ConditionalCompositeContract":
        raw_fields = d.get("fields")
        if not isinstance(raw_fields, dict) or not raw_fields:
            raise ContractError("composite payload needs a non-empty "
                                "'fields' dict", code="missing_fields")
        raw_conds = d.get("conditions", {})
        if not isinstance(raw_conds, dict):
            raise ContractError("'conditions' must be a dict",
                                code="bad_conditions")
        return cls(
            fields={n: cls._field_from_dict(v)
                    for n, v in raw_fields.items()},
            conditions={n: FieldCondition.from_dict(v)
                        for n, v in raw_conds.items()},
            **common)

    def describe(self) -> str:
        base = super().describe().replace(
            "composite contract", "conditional-composite contract")
        n_cond = len(self.conditions)
        return f"{base}; {n_cond} conditional field(s)"
