"""Context schemas — typed contracts for decision context.

Gjallarbrú slice 041.

``HugrGate.decide(state, spec, policy, context)`` accepts an opaque
``context`` mapping that nothing validates: a backend expecting
``context["locale"]`` to be a string gets whatever the caller passed.
This module adds:

- :class:`ContextField`: one named field — ``type`` (``string``,
  ``number``, ``integer``, ``boolean``, ``array``, ``object``, ``any``)
  plus ``required``;
- :class:`ContextSchema`: an ordered field set with ``allow_extra``
  control; :meth:`violations` aggregates every problem, :meth:`validate`
  raises one error;
- :class:`ContextContract` (kind ``"context-schema"``): the schema as a
  v2 contract, so context requirements travel, negotiate, and compose
  like any other contract.

(``hugrgate/validation.py`` is deliberately untouched: the contracts
layer may not import the contract-engine layer per the slice-004
layering rules. Runtime wiring of context schemas into ``decide()``
lands in slice 050.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Mapping, Optional, Tuple

from hugrgate.contracts.schema import (
    DecisionContract,
    register_kind,
)
from hugrgate.errors import ContractError

__all__ = [
    "CONTEXT_FIELD_TYPES",
    "ContextField",
    "ContextSchema",
    "ContextContract",
]

#: Types a context field may declare.
CONTEXT_FIELD_TYPES = (
    "string", "number", "integer", "boolean", "array", "object", "any",
)


def _type_ok(declared: str, value: Any) -> bool:
    if declared == "any":
        return True
    if declared == "string":
        return isinstance(value, str)
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared == "array":
        return isinstance(value, (list, tuple))
    if declared == "object":
        return isinstance(value, Mapping)
    return False  # pragma: no cover - guarded by constructor


@dataclass(frozen=True)
class ContextField:
    """One named, typed, optionally-required context field."""

    name: str
    type: str = "any"
    required: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ContractError("context field name must be a non-empty "
                                "string", code="bad_context_field")
        if self.type not in CONTEXT_FIELD_TYPES:
            raise ContractError(
                f"unknown context field type {self.type!r}; types: "
                f"{list(CONTEXT_FIELD_TYPES)}",
                code="bad_context_field_type")
        if not isinstance(self.required, bool):
            raise ContractError("'required' must be a bool",
                                code="bad_context_field")

    def check(self, value: Any) -> Optional[str]:
        """Violation message for one value, or None when it fits."""
        if not _type_ok(self.type, value):
            return (f"context field {self.name!r} must be "
                    f"{self.type}, got {type(value).__name__}")
        return None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"name": self.name, "type": self.type}
        if self.required:
            d["required"] = True
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "ContextField":
        if not isinstance(d, Mapping):
            raise ContractError("context field must be a mapping",
                                code="bad_context_field")
        try:
            return cls(name=d["name"], type=d.get("type", "any"),
                       required=d.get("required", False))
        except KeyError as e:
            raise ContractError(f"context field missing key: {e}",
                                code="bad_context_field") from None


class ContextSchema:
    """An ordered set of context fields with extra-key control."""

    __slots__ = ("_fields", "_allow_extra")

    def __init__(self, fields: List[ContextField],
                 allow_extra: bool = True) -> None:
        if not isinstance(fields, list):
            raise ContractError("'fields' must be a list",
                                code="bad_context_schema")
        for f in fields:
            if not isinstance(f, ContextField):
                raise ContractError(
                    "schema fields must be ContextField instances",
                    code="bad_context_schema")
        names = [f.name for f in fields]
        if len(set(names)) != len(names):
            raise ContractError(f"duplicate context field names: {names}",
                                code="bad_context_schema")
        if not isinstance(allow_extra, bool):
            raise ContractError("'allow_extra' must be a bool",
                                code="bad_context_schema")
        self._fields = tuple(fields)
        self._allow_extra = allow_extra

    @property
    def fields(self) -> Tuple[ContextField, ...]:
        """Declared fields in order."""
        return self._fields

    @property
    def allow_extra(self) -> bool:
        """Whether undeclared keys are permitted."""
        return self._allow_extra

    @property
    def required_fields(self) -> Tuple[str, ...]:
        """Names of required fields."""
        return tuple(f.name for f in self._fields if f.required)

    def violations(self, context: Any) -> List[str]:
        """Every schema problem with ``context`` (possibly empty)."""
        if isinstance(context, str) or not isinstance(context, Mapping):
            return [f"context must be a mapping, got "
                    f"{type(context).__name__}"]
        problems: List[str] = []
        for f in self._fields:
            if f.name not in context:
                if f.required:
                    problems.append(
                        f"missing required context field: {f.name!r}")
                continue
            msg = f.check(context[f.name])
            if msg is not None:
                problems.append(msg)
        if not self._allow_extra:
            extra = [k for k in context
                     if k not in {f.name for f in self._fields}]
            if extra:
                problems.append(f"undeclared context fields: {extra}")
        return problems

    def validate(self, context: Any) -> None:
        """Raise ContractError aggregating every violation."""
        problems = self.violations(context)
        if problems:
            raise ContractError(
                f"{len(problems)} context violation(s):\n" +
                "\n".join(f"  - {p}" for p in problems),
                code="context_violation", violations=problems)

    def to_dict(self) -> Dict[str, Any]:
        return {"fields": [f.to_dict() for f in self._fields],
                "allow_extra": self._allow_extra}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "ContextSchema":
        if not isinstance(d, Mapping):
            raise ContractError("context schema must be a mapping",
                                code="bad_context_schema")
        raw = d.get("fields", [])
        if not isinstance(raw, list):
            raise ContractError("'fields' must be a list",
                                code="bad_context_schema")
        return cls(fields=[ContextField.from_dict(v) for v in raw],
                   allow_extra=d.get("allow_extra", True))

    def __eq__(self, other: Any) -> bool:
        return (isinstance(other, ContextSchema)
                and self._fields == other._fields
                and self._allow_extra == other._allow_extra)

    def __repr__(self) -> str:
        return (f"ContextSchema(fields={[f.name for f in self._fields]!r}, "
                f"allow_extra={self._allow_extra})")


@register_kind
@dataclass
class ContextContract(DecisionContract):
    """A context schema as a v2 contract (kind ``"context-schema"``).

    The "decision value" here is the context mapping itself.
    """

    kind: ClassVar[str] = "context-schema"

    fields: List[Dict[str, Any]] = field(default_factory=list)
    allow_extra: bool = True
    _schema: ContextSchema = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        try:
            schema = ContextSchema(
                fields=[ContextField.from_dict(v) for v in self.fields],
                allow_extra=self.allow_extra)
        except ContractError as e:
            raise ContractError(f"invalid context schema: {e.message}",
                                code=e.details.get("code",
                                                   "bad_context_schema"))
        self._schema = schema
        # Normalize stored form through the schema.
        self.fields = [f.to_dict() for f in schema.fields]
        self.allow_extra = schema.allow_extra

    @property
    def schema(self) -> ContextSchema:
        """The validated context schema."""
        return self._schema

    def validate_value(self, value: Any) -> None:
        self._schema.validate(value)

    def violations(self, value: Any) -> List[str]:
        """Non-raising validation of a context mapping."""
        return self._schema.violations(value)

    def _payload_dict(self) -> Dict[str, Any]:
        return {"fields": [dict(v) for v in self.fields],
                "allow_extra": self.allow_extra}

    @classmethod
    def _from_payload(cls, d: Mapping[str, Any],
                      common: Dict[str, Any]) -> "ContextContract":
        raw = d.get("fields", [])
        if not isinstance(raw, list):
            raise ContractError("context-schema payload needs a 'fields' "
                                "list", code="missing_fields")
        allow_extra = d.get("allow_extra", True)
        if not isinstance(allow_extra, bool):
            raise ContractError("'allow_extra' must be a bool",
                                code="bad_context_schema")
        return cls(fields=raw, allow_extra=allow_extra, **common)

    def describe(self) -> str:
        req = len(self._schema.required_fields)
        return (f"context-schema contract {self.name or self.contract_id!r}: "
                f"{len(self._schema.fields)} field(s), {req} required, "
                f"extra {'allowed' if self.allow_extra else 'rejected'}")
