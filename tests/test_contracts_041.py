"""Gjallarbrú slice 041 — context schemas."""

from __future__ import annotations

import pytest

from hugrgate.contracts.context import (
    ContextContract,
    ContextField,
    ContextSchema,
)
from hugrgate.contracts.schema import contract_from_dict
from hugrgate.errors import ContractError


def _schema() -> ContextSchema:
    return ContextSchema(
        fields=[
            ContextField("locale", "string", required=True),
            ContextField("channel", "string"),
            ContextField("priority", "integer"),
            ContextField("score", "number"),
            ContextField("vip", "boolean"),
            ContextField("tags", "array"),
            ContextField("meta", "object"),
        ],
        allow_extra=False,
    )


# --- success ---------------------------------------------------------------

def test_valid_context():
    _schema().validate({"locale": "en", "channel": "web", "priority": 3,
                        "score": 0.5, "vip": True, "tags": ["a"],
                        "meta": {"k": 1}})
    assert _schema().violations({"locale": "en"}) == []


def test_optional_fields_may_be_absent():
    s = ContextSchema(fields=[ContextField("x", "string")])
    s.validate({})


def test_type_matrix():
    cases = [("string", "s", True), ("string", 1, False),
             ("number", 1.5, True), ("number", True, False),
             ("integer", 3, True), ("integer", 3.0, False),
             ("integer", True, False), ("boolean", False, True),
             ("boolean", 1, False), ("array", [1], True),
             ("array", (1,), True), ("array", "s", False),
             ("object", {"a": 1}, True), ("object", [1], False),
             ("any", object(), True)]
    for declared, value, ok in cases:
        f = ContextField("f", declared)
        assert (f.check(value) is None) == ok, (declared, value)


def test_contract_validate_value():
    c = ContextContract(contract_id="ctx-1",
                        fields=[{"name": "locale", "type": "string",
                                 "required": True}],
                        allow_extra=True)
    c.validate_value({"locale": "en", "other": 1})
    assert c.violations({"locale": "en"}) == []


def test_round_trip():
    c = ContextContract(contract_id="ctx-1",
                        fields=[f.to_dict() for f in _schema().fields],
                        allow_extra=False)
    back = contract_from_dict(c.to_dict())
    assert isinstance(back, ContextContract)
    assert back.to_dict() == c.to_dict()
    assert back.schema == c.schema


def test_schema_equality():
    assert _schema() == ContextSchema.from_dict(_schema().to_dict())


def test_required_fields_property():
    assert _schema().required_fields == ("locale",)


def test_describe():
    assert "7 field(s)" in ContextContract(
        contract_id="x",
        fields=[f.to_dict() for f in _schema().fields]).describe()


# --- failure ---------------------------------------------------------------

def test_missing_required():
    with pytest.raises(ContractError) as ei:
        _schema().validate({"channel": "web"})
    assert ei.value.details["code"] == "context_violation"


def test_wrong_types_aggregated():
    s = _schema()
    problems = s.violations({"locale": 1, "priority": "high"})
    assert len(problems) == 2


def test_extra_rejected_when_disallowed():
    with pytest.raises(ContractError):
        _schema().validate({"locale": "en", "zzz": 1})


def test_non_mapping_rejected():
    with pytest.raises(ContractError):
        _schema().validate("nope")
    with pytest.raises(ContractError):
        _schema().validate(None)


def test_bad_field_type_rejected():
    with pytest.raises(ContractError):
        ContextField("x", "uuid")


def test_duplicate_field_names_rejected():
    with pytest.raises(ContractError):
        ContextSchema(fields=[ContextField("x"), ContextField("x")])


def test_empty_field_name_rejected():
    with pytest.raises(ContractError):
        ContextField("", "string")


def test_non_bool_required_rejected():
    with pytest.raises(ContractError):
        ContextField("x", "string", required="yes")  # type: ignore[arg-type]


def test_contract_bad_payload():
    with pytest.raises(ContractError):
        ContextContract(contract_id="x", fields="nope")  # type: ignore[arg-type]


# --- boundary ----------------------------------------------------------------

def test_empty_schema():
    s = ContextSchema(fields=[])
    s.validate({"anything": 1})
    assert s.required_fields == ()


def test_allow_extra_true_by_default():
    s = ContextSchema(fields=[ContextField("a", "string", required=True)])
    s.validate({"a": "x", "b": 1, "c": 2})
