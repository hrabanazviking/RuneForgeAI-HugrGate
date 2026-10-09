"""Structured composite decisions. Gjallarbrú slice 030.

A composite contract is one structured judgment made of named fields,
each field governed by its own contract: e.g. ``{"severity": <ordinal>,
"department": <categorical>, "eta_minutes": <numeric>}``.

Fields may be v2 :class:`DecisionContract`s *or* v1
:class:`hugrgate.spec.DecisionSpec`s — the composite bridges both
generations of the contract system (full v1→v2 migration is slice 047).
Values are mappings with exactly the declared fields: missing and
unknown fields are both rejected, so typos never slip through silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Mapping, Union

from hugrgate.contracts.schema import (
    DecisionContract,
    contract_from_dict,
    register_kind,
)
from hugrgate.errors import ContractError
from hugrgate.spec import DecisionSpec

__all__ = [
    "FieldContract",
    "CompositeContract",
]

#: What may govern one composite field.
FieldContract = Union[DecisionContract, DecisionSpec]


def _check_name(name: object) -> str:
    if not isinstance(name, str) or not name:
        raise ContractError(f"field name must be a non-empty string, "
                            f"got {name!r}", code="bad_field_name")
    return name


def _validate_spec_value(spec: DecisionSpec, value: Any, *,
                         field_name: str) -> None:
    """Validate one raw value against a v1 DecisionSpec."""
    space = spec.value_space()
    if spec.type == "numeric":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ContractError(
                f"field {field_name!r}: numeric value must be a number, "
                f"got {type(value).__name__}", code="field_type_mismatch")
        assert spec.minimum is not None and spec.maximum is not None
        if not (spec.minimum <= value <= spec.maximum):
            raise ContractError(
                f"field {field_name!r}: {value} outside "
                f"[{spec.minimum}, {spec.maximum}]",
                code="field_out_of_range")
        return
    if spec.type == "multilabel":
        if not isinstance(value, list):
            raise ContractError(
                f"field {field_name!r}: multilabel value must be a list",
                code="field_type_mismatch")
        bad = [v for v in value if v not in space]
        if bad:
            raise ContractError(
                f"field {field_name!r}: labels outside spec: {bad}",
                code="field_value_not_in_space")
        return
    if value not in space:
        raise ContractError(
            f"field {field_name!r}: {value!r} not in {space}",
            code="field_value_not_in_space")


@register_kind
@dataclass
class CompositeContract(DecisionContract):
    """One structured judgment: named fields, each with its own contract."""

    kind: ClassVar[str] = "composite"

    fields: Dict[str, FieldContract] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.fields, dict) or not self.fields:
            raise ContractError("composite contract needs ≥1 field",
                                code="no_fields")
        clean: Dict[str, FieldContract] = {}
        for name, sub in self.fields.items():
            _check_name(name)
            if not isinstance(sub, (DecisionContract, DecisionSpec)):
                raise ContractError(
                    f"field {name!r} must be a DecisionContract or "
                    f"DecisionSpec, got {type(sub).__name__}",
                    code="bad_field_contract")
            clean[name] = sub
        self.fields = clean

    # -- structure ---------------------------------------------------------

    def field_names(self) -> List[str]:
        """Declared field names in definition order."""
        return list(self.fields)

    def field_contract(self, name: str) -> FieldContract:
        """The contract governing field ``name``."""
        try:
            return self.fields[name]
        except KeyError:
            raise ContractError(
                f"unknown field {name!r}; fields: {self.field_names()}",
                code="unknown_field") from None

    # -- validation ----------------------------------------------------------

    def validate_value(self, value: Any) -> None:
        if isinstance(value, str) or not isinstance(value, Mapping):
            raise ContractError(
                "composite value must be a mapping of field -> value, "
                f"got {type(value).__name__}", code="composite_not_mapping")
        missing = [n for n in self.fields if n not in value]
        if missing:
            raise ContractError(f"composite value missing fields: {missing}",
                                code="missing_fields", missing=missing)
        unknown = [k for k in value if k not in self.fields]
        if unknown:
            raise ContractError(
                f"composite value has undeclared fields: {unknown}",
                code="unknown_fields", unknown=unknown)
        for name, sub in self.fields.items():
            try:
                if isinstance(sub, DecisionContract):
                    sub.validate_value(value[name])
                else:
                    _validate_spec_value(sub, value[name], field_name=name)
            except ContractError as e:
                raise ContractError(
                    f"field {name!r}: {e.message}",
                    code=e.details.get("code", "field_invalid"),
                    field=name) from None

    # -- serialization ---------------------------------------------------------

    @staticmethod
    def _field_to_dict(sub: FieldContract) -> Dict[str, Any]:
        if isinstance(sub, DecisionContract):
            return sub.to_dict()
        return {"decision_spec": sub.to_dict()}

    @staticmethod
    def _field_from_dict(d: Any) -> FieldContract:
        if not isinstance(d, dict):
            raise ContractError(f"field payload must be a dict, got {d!r}",
                                code="bad_field_payload")
        if "kind" in d:
            return contract_from_dict(d)
        if "decision_spec" in d:
            return DecisionSpec.from_dict(d["decision_spec"])
        # Bare v1 spec dict (has "type", no wrapper): accept for leniency.
        if "type" in d:
            return DecisionSpec.from_dict(d)
        raise ContractError(
            "field payload needs 'kind' (v2 contract) or 'decision_spec'/'type' "
            f"(v1 spec), got keys {sorted(d)}", code="bad_field_payload")

    def _payload_dict(self) -> Dict[str, Any]:
        return {"fields": {n: self._field_to_dict(s)
                           for n, s in self.fields.items()}}

    @classmethod
    def _from_payload(cls, d: Mapping[str, Any],
                      common: Dict[str, Any]) -> "CompositeContract":
        raw = d.get("fields")
        if not isinstance(raw, dict) or not raw:
            raise ContractError("composite payload needs a non-empty "
                                "'fields' dict", code="missing_fields")
        return cls(fields={n: cls._field_from_dict(v)
                           for n, v in raw.items()}, **common)

    def describe(self) -> str:
        inner = ", ".join(
            f"{n}: {s.kind if isinstance(s, DecisionContract) else 'spec/' + s.type}"
            for n, s in self.fields.items())
        return (f"composite contract {self.name or self.contract_id!r}: "
                f"{len(self.fields)} fields ({inner})")
