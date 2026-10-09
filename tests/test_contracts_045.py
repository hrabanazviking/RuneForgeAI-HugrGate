"""Gjallarbrú slice 045 — contract composition."""

from __future__ import annotations

import pytest

from hugrgate.contracts.composite import CompositeContract
from hugrgate.contracts.composition import merge, product, with_deadline
from hugrgate.contracts.conditional import (
    ConditionalCompositeContract,
    FieldCondition,
)
from hugrgate.contracts.crossfield import (
    ConstrainedCompositeContract,
    FieldConstraint,
)
from hugrgate.contracts.deadlines import TimedContract
from hugrgate.contracts.ordinal import OrdinalContract
from hugrgate.contracts.schema import contract_from_dict
from hugrgate.errors import ContractError
from hugrgate.spec import DecisionSpec


def _a() -> CompositeContract:
    return CompositeContract(
        contract_id="a",
        fields={"x": DecisionSpec(type="binary", statement="x"),
                "y": DecisionSpec(type="binary", statement="y")})


def _b() -> CompositeContract:
    return CompositeContract(
        contract_id="b",
        fields={"y": DecisionSpec(type="binary", statement="y"),
                "z": DecisionSpec(type="numeric", minimum=0, maximum=1)})


# --- merge ---------------------------------------------------------------

def test_merge_unions_fields():
    m = merge(_a(), _b(), contract_id="m")
    assert m.field_names() == ["x", "y", "z"]
    m.validate_value({"x": "true", "y": "false", "z": 0.5})


def test_merge_identical_fields_no_conflict():
    m = merge(_a(), _a(), contract_id="m")  # same field, same contract
    assert m.field_names() == ["x", "y"]


def test_merge_conflict_error_by_default():
    other = CompositeContract(
        contract_id="c",
        fields={"y": DecisionSpec(type="categorical",
                                  options=["p", "q"])})
    with pytest.raises(ContractError) as ei:
        merge(_a(), other, contract_id="m")
    assert ei.value.details["code"] == "merge_conflict"


def test_merge_conflict_policies():
    other = CompositeContract(
        contract_id="c",
        fields={"y": DecisionSpec(type="categorical",
                                  options=["p", "q"])})
    left = merge(_a(), other, contract_id="m", on_conflict="left")
    assert left.field_contract("y") == \
        DecisionSpec(type="binary", statement="y")
    right = merge(_a(), other, contract_id="m", on_conflict="right")
    assert right.field_contract("y") == \
        DecisionSpec(type="categorical", options=["p", "q"])


def test_merge_conditional_unions_conditions():
    c1 = ConditionalCompositeContract(
        contract_id="c1",
        fields={"a": DecisionSpec(type="binary", statement="a"),
                "b": DecisionSpec(type="binary", statement="b")},
        conditions={"b": FieldCondition("a", "eq", "true")})
    c2 = ConditionalCompositeContract(
        contract_id="c2",
        fields={"a": DecisionSpec(type="binary", statement="a"),
                "c": DecisionSpec(type="binary", statement="c")},
        conditions={"c": FieldCondition("a", "eq", "false")})
    m = merge(c1, c2, contract_id="m")
    assert isinstance(m, ConditionalCompositeContract)
    assert set(m.conditions) == {"b", "c"}
    m.validate_value({"a": "true", "b": "true"})
    m.validate_value({"a": "false", "c": "false"})


def test_merge_constrained_concatenates():
    k1 = ConstrainedCompositeContract(
        contract_id="k1",
        fields={"a": DecisionSpec(type="numeric", minimum=0, maximum=10)},
        constraints=[FieldConstraint(("a",), "ge", 1)])
    k2 = ConstrainedCompositeContract(
        contract_id="k2",
        fields={"a": DecisionSpec(type="numeric", minimum=0, maximum=10)},
        constraints=[FieldConstraint(("a",), "le", 9)])
    m = merge(k1, k2, contract_id="m")
    assert isinstance(m, ConstrainedCompositeContract)
    assert len(m.constraints) == 2
    m.validate_value({"a": 5})
    with pytest.raises(ContractError):
        m.validate_value({"a": 0})


def test_merge_heterogeneous_rejected():
    with pytest.raises(ContractError) as ei:
        merge(_a(),
              ConditionalCompositeContract(
                  contract_id="c",
                  fields={"q": DecisionSpec(type="binary", statement="q")}),
              contract_id="m")
    assert ei.value.details["code"] == "heterogeneous_merge"


def test_merge_needs_two():
    with pytest.raises(ContractError):
        merge(_a(), contract_id="m")


def test_merge_bad_policy():
    with pytest.raises(ContractError):
        merge(_a(), _b(), contract_id="m", on_conflict="chaos")


def test_merge_round_trip():
    m = merge(_a(), _b(), contract_id="m")
    back = contract_from_dict(m.to_dict())
    assert back.to_dict() == m.to_dict()


# --- product ---------------------------------------------------------------

def test_product_joint_decision():
    p = product(OrdinalContract(contract_id="o", levels=["lo", "hi"]),
                DecisionSpec(type="binary", statement="go?"),
                contract_id="p", name_a="level", name_b="go")
    assert isinstance(p, CompositeContract)
    p.validate_value({"level": "hi", "go": "true"})
    with pytest.raises(ContractError):
        p.validate_value({"level": "hi"})


def test_product_same_names_rejected():
    with pytest.raises(ContractError):
        product(_a(), _b(), contract_id="p", name_a="x", name_b="x")


def test_product_bad_arg_rejected():
    with pytest.raises(ContractError):
        product(_a(), "nope", contract_id="p")  # type: ignore[arg-type]


# --- with_deadline ---------------------------------------------------------------

def test_with_deadline_stacks():
    t = with_deadline(OrdinalContract(contract_id="o", levels=["lo", "hi"]),
                      contract_id="t", budget_ms=250.0)
    assert isinstance(t, TimedContract)
    assert t.budget_ms == 250.0
    t.validate_value("lo")
    t.check_timing(1000.0, 1000.1)


def test_with_deadline_bad_arg():
    with pytest.raises(ContractError):
        with_deadline("nope", contract_id="t",  # type: ignore[arg-type]
                      budget_ms=10)
