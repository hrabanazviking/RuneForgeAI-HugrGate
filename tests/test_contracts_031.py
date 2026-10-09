"""Gjallarbrú slice 031 — conditional decision fields."""

from __future__ import annotations

import pytest

from hugrgate.contracts.composite import CompositeContract
from hugrgate.contracts.conditional import (
    ConditionalCompositeContract,
    FieldCondition,
)
from hugrgate.contracts.schema import contract_from_dict
from hugrgate.errors import ContractError
from hugrgate.spec import DecisionSpec


def _clinic() -> ConditionalCompositeContract:
    return ConditionalCompositeContract(
        contract_id="clinic-1",
        fields={
            "has_allergy": DecisionSpec(type="binary",
                                        statement="patient has an allergy"),
            "allergy_details": DecisionSpec(type="categorical",
                                            options=["penicillin", "latex",
                                                     "other"]),
            "severity": DecisionSpec(type="ordinal",
                                     levels=["low", "medium", "high"]),
            "epinephrine_mg": DecisionSpec(type="numeric", minimum=0.0,
                                            maximum=1.0),
        },
        conditions={
            "allergy_details": FieldCondition("has_allergy", "eq", "true"),
            "epinephrine_mg": FieldCondition("severity", "eq", "high"),
        },
    )


# --- success ---------------------------------------------------------------

def test_no_allergy_needs_no_details():
    c = _clinic()
    v = {"has_allergy": "false", "severity": "low"}
    c.validate_value(v)
    assert c.check_value(v) == []


def test_allergy_requires_details():
    c = _clinic()
    c.validate_value({"has_allergy": "true", "allergy_details": "latex",
                      "severity": "medium"})


def test_chained_conditions():
    c = ConditionalCompositeContract(
        contract_id="chain",
        fields={
            "a": DecisionSpec(type="binary", statement="a"),
            "b": DecisionSpec(type="binary", statement="b"),
            "c": DecisionSpec(type="binary", statement="c"),
        },
        conditions={
            "b": FieldCondition("a", "eq", "true"),
            "c": FieldCondition("b", "eq", "true"),  # cascade via b
        },
    )
    c.validate_value({"a": "true", "b": "true", "c": "false"})
    c.validate_value({"a": "false"})  # b, c cascade inactive
    with pytest.raises(ContractError):
        c.validate_value({"a": "true"})  # b active but missing


def test_comparison_ops():
    c = ConditionalCompositeContract(
        contract_id="ops",
        fields={
            "age": DecisionSpec(type="numeric", minimum=0, maximum=120),
            "senior_note": DecisionSpec(type="binary", statement="s"),
            "minor_note": DecisionSpec(type="binary", statement="m"),
            "dept": DecisionSpec(type="categorical",
                                 options=["er", "icu", "ward"]),
            "trauma_note": DecisionSpec(type="binary", statement="t"),
        },
        conditions={
            "senior_note": FieldCondition("age", "ge", 65),
            "minor_note": FieldCondition("age", "lt", 18),
            "trauma_note": FieldCondition("dept", "in", ["er", "icu"]),
        },
    )
    assert c.active_fields({"age": 70, "dept": "ward"}) == [
        "age", "senior_note", "dept"]
    assert c.active_fields({"age": 10, "dept": "er"}) == [
        "age", "minor_note", "dept", "trauma_note"]


def test_in_op():
    cond = FieldCondition("dept", "in", ["er", "icu"])
    assert cond.satisfied_by("er")
    assert not cond.satisfied_by("ward")
    with pytest.raises(ContractError):
        FieldCondition("d", "in", "er")  # a string is not a collection


def test_activation_report():
    c = _clinic()
    rep = c.activation_report({"has_allergy": "true", "severity": "low"})
    assert rep == {"has_allergy": True, "allergy_details": True,
                   "severity": True, "epinephrine_mg": False}


def test_round_trip():
    c = _clinic()
    back = contract_from_dict(c.to_dict())
    assert isinstance(back, ConditionalCompositeContract)
    assert back.to_dict() == c.to_dict()
    back.validate_value({"has_allergy": "true",
                         "allergy_details": "other", "severity": "high",
                         "epinephrine_mg": 0.3})


def test_condition_to_from_dict():
    cond = FieldCondition("a", "in", {"x", "y"})
    assert FieldCondition.from_dict(cond.to_dict()).satisfied_by("x")


def test_describe():
    assert "2 conditional" in _clinic().describe()


# --- failure ---------------------------------------------------------------

def test_missing_active_conditional_field():
    with pytest.raises(ContractError) as ei:
        _clinic().validate_value({"has_allergy": "true", "severity": "low"})
    assert ei.value.details["code"] == "missing_fields"


def test_inactive_field_provided_rejected():
    with pytest.raises(ContractError) as ei:
        _clinic().validate_value({"has_allergy": "false",
                                  "allergy_details": "latex",
                                  "severity": "low"})
    assert ei.value.details["code"] == "inactive_field_provided"


def test_condition_cycle_rejected():
    with pytest.raises(ContractError) as ei:
        ConditionalCompositeContract(
            contract_id="cyc",
            fields={"a": DecisionSpec(type="binary", statement="a"),
                    "b": DecisionSpec(type="binary", statement="b")},
            conditions={"a": FieldCondition("b", "eq", "true"),
                        "b": FieldCondition("a", "eq", "true")})
    assert ei.value.details["code"] == "condition_cycle"


def test_self_reference_rejected():
    with pytest.raises(ContractError):
        ConditionalCompositeContract(
            contract_id="self",
            fields={"a": DecisionSpec(type="binary", statement="a")},
            conditions={"a": FieldCondition("a", "eq", "true")})


def test_condition_on_unknown_field_rejected():
    with pytest.raises(ContractError):
        ConditionalCompositeContract(
            contract_id="u",
            fields={"a": DecisionSpec(type="binary", statement="a")},
            conditions={"a": FieldCondition("zzz", "eq", "true")})


def test_condition_target_unknown_field_rejected():
    with pytest.raises(ContractError):
        ConditionalCompositeContract(
            contract_id="u",
            fields={"a": DecisionSpec(type="binary", statement="a")},
            conditions={"zzz": FieldCondition("a", "eq", "true")})


def test_bad_op_rejected():
    with pytest.raises(ContractError):
        FieldCondition("a", "approx", 1)


def test_type_mismatch_in_condition():
    cond = FieldCondition("age", "gt", 18)
    with pytest.raises(ContractError):
        cond.satisfied_by("old")


def test_bad_field_value_still_rejected():
    with pytest.raises(ContractError):
        _clinic().validate_value({"has_allergy": "true",
                                  "allergy_details": "peanuts",
                                  "severity": "low"})


# --- boundary ----------------------------------------------------------------

def test_partial_value_activation():
    c = _clinic()
    # severity undecided: epinephrine_mg cannot activate yet
    assert c.active_fields({"has_allergy": "true"}) == [
        "has_allergy", "allergy_details", "severity"]


def test_ne_op():
    cond = FieldCondition("m", "ne", "none")
    assert cond.satisfied_by("aspirin")
    assert not cond.satisfied_by("none")


def test_condition_from_dict_missing_key():
    with pytest.raises(ContractError):
        FieldCondition.from_dict({"on_field": "a"})


def test_is_composite_subclass():
    assert isinstance(_clinic(), CompositeContract)
    assert _clinic().kind == "conditional-composite"
