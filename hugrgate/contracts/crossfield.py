"""Cross-field constraints — invariants over whole decisions.

Gjallarbrú slice 032.

Conditional fields (slice 031) decide *whether* a field is active. They
cannot state *invariants* spanning fields: ``start < end``,
``a + b <= 100``, "these three codes are pairwise distinct". This module
adds declarative, serializable constraints evaluated after per-field
validation:

- :class:`FieldConstraint`: one invariant — ``fields`` involved, an
  ``op``, and a ``target`` (a literal, or ``{"field": name}`` to compare
  against another field's value);
- :class:`ConstrainedCompositeContract` (kind ``"constrained-composite"``):
  a composite with a ``constraints`` list; :meth:`validate_value`
  aggregates *every* violation into one error instead of failing fast.

Constraints are data, not callables: they serialize, describe
themselves, and stay auditable (law 14: bounded, typed, auditable).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from hugrgate.contracts.composite import CompositeContract
from hugrgate.contracts.schema import register_kind
from hugrgate.errors import ContractError

__all__ = [
    "CONSTRAINT_OPS",
    "ConstrainedCompositeContract",
    "FieldConstraint",
]

#: Comparison ops take exactly one field; sum ops take ≥1; distinct takes ≥2.
CONSTRAINT_OPS = (
    "lt", "le", "eq", "ne", "gt", "ge",
    "sum_lt", "sum_le", "sum_eq", "sum_ge", "sum_gt",
    "all_distinct",
)


def _is_field_ref(target: Any) -> bool:
    return (isinstance(target, dict) and set(target) == {"field"}
            and isinstance(target["field"], str))


@dataclass(frozen=True)
class FieldConstraint:
    """One declarative invariant over a composite decision's fields."""

    fields: tuple[str, ...]
    op: str
    target: Any = None
    description: str = ""

    def __post_init__(self) -> None:
        if not self.fields or not all(
                isinstance(f, str) and f for f in self.fields):
            raise ContractError("constraint needs ≥1 non-empty field name",
                                code="bad_constraint_fields")
        if len(set(self.fields)) != len(self.fields):
            raise ContractError("constraint fields must be unique",
                                code="bad_constraint_fields")
        if self.op not in CONSTRAINT_OPS:
            raise ContractError(
                f"unknown constraint op {self.op!r}; "
                f"ops: {list(CONSTRAINT_OPS)}", code="bad_constraint_op")
        if self.op in ("lt", "le", "eq", "ne", "gt", "ge"):
            if len(self.fields) != 1:
                raise ContractError(
                    f"op {self.op!r} takes exactly one field",
                    code="bad_constraint_arity")
            if self.target is None:
                raise ContractError(
                    f"op {self.op!r} needs a target literal or "
                    f'{{"field": name}}', code="missing_constraint_target")
        elif self.op.startswith("sum_"):
            if isinstance(self.target, bool) or not isinstance(
                    self.target, (int, float)):
                raise ContractError(
                    f"op {self.op!r} needs a numeric target",
                    code="bad_constraint_target")
        elif self.op == "all_distinct":
            if len(self.fields) < 2:
                raise ContractError("all_distinct needs ≥2 fields",
                                    code="bad_constraint_arity")
            if self.target is not None:
                raise ContractError("all_distinct takes no target",
                                    code="bad_constraint_target")
        if not isinstance(self.description, str):
            raise ContractError("constraint description must be a string",
                                code="bad_constraint_description")

    # -- evaluation --------------------------------------------------------

    def _resolve_target(self, value: Mapping[str, Any]) -> tuple[bool, Any]:
        """Resolve the target to a concrete value.

        Returns ``(True, resolved)`` or ``(False, missing_field_name)`` —
        never raises on bad data (control flow via return, not exceptions).
        """
        if _is_field_ref(self.target):
            name = self.target["field"]
            if name not in value:
                return False, name
            return True, value[name]
        return True, self.target

    def check(self, value: Mapping[str, Any]) -> str | None:
        """Return a violation message, or None when satisfied.

        Never raises on bad data — missing fields and type mismatches
        become violation messages, so validators can aggregate.
        """
        missing = [f for f in self.fields if f not in value]
        if missing:
            return (f"constraint {self.describe()}: missing fields "
                    f"{missing}")
        found, target = self._resolve_target(value)
        if not found:
            return (f"constraint {self.describe()}: referenced field "
                    f"{target!r} missing")
        try:
            if self.op == "all_distinct":
                vals = [value[f] for f in self.fields]
                seen: list[Any] = []
                for v in vals:
                    if any(v == s and type(v) is type(s) for s in seen):
                        return (f"constraint {self.describe()}: fields "
                                f"{list(self.fields)} are not all distinct")
                    seen.append(v)
                return None
            if self.op.startswith("sum_"):
                total = 0.0
                for f in self.fields:
                    v = value[f]
                    if isinstance(v, bool) or not isinstance(v, (int, float)):
                        return (f"constraint {self.describe()}: field {f!r} "
                                f"is not numeric ({v!r})")
                    total += v
                cmp_op = self.op[4:]
                ok = _compare(cmp_op, total, target)
            else:
                ok = _compare(self.op, value[self.fields[0]], target)
        except TypeError as e:
            return f"constraint {self.describe()}: incomparable values ({e})"
        if ok:
            return None
        left = ("sum(" + ", ".join(self.fields) + ")"
                if self.op.startswith("sum_") else self.fields[0])
        t = (f"field {self.target['field']!r}" if _is_field_ref(self.target)
             else repr(target))
        return (f"constraint violated: {left} {self._symbol()} {t} "
                f"(values: { {f: value[f] for f in self.fields} })"
                + (f" — {self.description}" if self.description else ""))

    def _symbol(self) -> str:
        return {"lt": "<", "le": "<=", "eq": "==", "ne": "!=",
                "gt": ">", "ge": ">="}[self.op[4:] if self.op.startswith("sum_")
                                       else self.op]

    def describe(self) -> str:
        """Human-readable invariant, e.g. ``start < field 'end'``."""
        if self.op == "all_distinct":
            s = f"all_distinct({', '.join(self.fields)})"
        elif self.op.startswith("sum_"):
            s = (f"sum({', '.join(self.fields)}) {self._symbol()} "
                 f"{self.target!r}")
        else:
            t = (f"field {self.target['field']!r}"
                 if _is_field_ref(self.target) else repr(self.target))
            s = f"{self.fields[0]} {self._symbol()} {t}"
        return f"{s} — {self.description}" if self.description else s

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"fields": list(self.fields), "op": self.op}
        if self.target is not None:
            d["target"] = self.target
        if self.description:
            d["description"] = self.description
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> FieldConstraint:
        if not isinstance(d, Mapping):
            raise ContractError("constraint must be a mapping",
                                code="bad_constraint")
        try:
            return cls(fields=tuple(d["fields"]), op=d["op"],
                       target=d.get("target"),
                       description=d.get("description", ""))
        except KeyError as e:
            raise ContractError(f"constraint missing key: {e}",
                                code="bad_constraint") from None



def _compare(op: str, left: Any, right: Any) -> bool:
    return {"lt": left < right, "le": left <= right,
            "eq": left == right, "ne": left != right,
            "gt": left > right, "ge": left >= right}[op]


@register_kind
@dataclass
class ConstrainedCompositeContract(CompositeContract):
    """A composite with cross-field invariants (kind
    ``"constrained-composite"``)."""

    kind: ClassVar[str] = "constrained-composite"

    constraints: list[FieldConstraint] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.constraints, list):
            raise ContractError("'constraints' must be a list",
                                code="bad_constraints")
        for c in self.constraints:
            if not isinstance(c, FieldConstraint):
                raise ContractError(
                    "constraints must be FieldConstraint instances, got "
                    f"{type(c).__name__}", code="bad_constraint")
            unknown = [f for f in c.fields if f not in self.fields]
            if unknown:
                raise ContractError(
                    f"constraint {c.describe()}: unknown fields {unknown}",
                    code="constraint_on_unknown_field")
            if _is_field_ref(c.target) and c.target["field"] not in self.fields:
                raise ContractError(
                    f"constraint {c.describe()}: target field "
                    f"{c.target['field']!r} unknown",
                    code="constraint_on_unknown_field")

    # -- validation ----------------------------------------------------------

    def violations(self, value: Mapping[str, Any]) -> list[str]:
        """Every constraint violation message for ``value`` (possibly empty)."""
        out = []
        for c in self.constraints:
            msg = c.check(value)
            if msg is not None:
                out.append(msg)
        return out

    def validate_value(self, value: Any) -> None:
        super().validate_value(value)
        assert isinstance(value, Mapping)
        problems = self.violations(value)
        if problems:
            raise ContractError(
                f"{len(problems)} cross-field constraint violation(s):\n" +
                "\n".join(f"  - {p}" for p in problems),
                code="cross_field_violation", violations=problems)

    # -- serialization ---------------------------------------------------------

    def _payload_dict(self) -> dict[str, Any]:
        d = super()._payload_dict()
        if self.constraints:
            d["constraints"] = [c.to_dict() for c in self.constraints]
        return d

    @classmethod
    def _from_payload(cls, d: Mapping[str, Any],
                      common: dict[str, Any]) -> ConstrainedCompositeContract:
        raw_fields = d.get("fields")
        if not isinstance(raw_fields, dict) or not raw_fields:
            raise ContractError("composite payload needs a non-empty "
                                "'fields' dict", code="missing_fields")
        raw_constraints = d.get("constraints", [])
        if not isinstance(raw_constraints, list):
            raise ContractError("'constraints' must be a list",
                                code="bad_constraints")
        return cls(
            fields={n: cls._field_from_dict(v)
                    for n, v in raw_fields.items()},
            constraints=[FieldConstraint.from_dict(v)
                         for v in raw_constraints],
            **common)

    def describe(self) -> str:
        base = super().describe().replace(
            "composite contract", "constrained-composite contract")
        return f"{base}; {len(self.constraints)} constraint(s)"
