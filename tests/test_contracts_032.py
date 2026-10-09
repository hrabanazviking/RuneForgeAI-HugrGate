"""Gjallarbrú slice 032 — cross-field constraints."""

from __future__ import annotations

import pytest

from hugrgate.contracts.crossfield import (
    ConstrainedCompositeContract,
    FieldConstraint,
)
from hugrgate.contracts.schema import contract_from_dict
from hugrgate.errors import ContractError
from hugrgate.spec import DecisionSpec


def _sched() -> ConstrainedCompositeContract:
    return ConstrainedCompositeContract(
        contract_id="sched-1",
        fields={
            "start": DecisionSpec(type="numeric", minimum=0, maximum=24),
            "end": DecisionSpec(type="numeric", minimum=0, maximum=24),
            "a": DecisionSpec(type="numeric", minimum=0, maximum=100),
            "b": DecisionSpec(type="numeric", minimum=0, maximum=100),
            "code1": DecisionSpec(type="categorical",
                                  options=["x", "y", "z"]),
            "code2": DecisionSpec(type="categorical",
                                  options=["x", "y", "z"]),
        },
        constraints=[
            FieldConstraint(("start",), "lt", {"field": "end"},
                            "shift starts before it ends"),
            FieldConstraint(("a", "b"), "sum_le", 100, "budget cap"),
            FieldConstraint(("code1", "code2"), "all_distinct"),
        ],
    )


def _good():
    return {"start": 9, "end": 17, "a": 40, "b": 50,
            "code1": "x", "code2": "y"}


# --- success ---------------------------------------------------------------

def test_valid_value_passes():
    c = _sched()
    c.validate_value(_good())
    assert c.violations(_good()) == []


def test_field_ref_target():
    c = FieldConstraint(("start",), "lt", {"field": "end"})
    assert c.check({"start": 1, "end": 2}) is None
    assert "field 'end'" in c.describe()


def test_sum_ops():
    assert FieldConstraint(("a", "b"), "sum_eq", 100).check(
        {"a": 60, "b": 40}) is None
    assert FieldConstraint(("a",), "sum_ge", 10).check({"a": 3}) is not None


def test_all_distinct():
    c = FieldConstraint(("p", "q", "r"), "all_distinct")
    assert c.check({"p": 1, "q": 2, "r": 3}) is None
    assert c.check({"p": 1, "q": 1, "r": 3}) is not None


def test_round_trip():
    c = _sched()
    back = contract_from_dict(c.to_dict())
    assert isinstance(back, ConstrainedCompositeContract)
    assert back.to_dict() == c.to_dict()
    back.validate_value(_good())


def test_constraint_dict_round_trip():
    c = FieldConstraint(("a", "b"), "sum_le", 100, "cap")
    assert FieldConstraint.from_dict(c.to_dict()).to_dict() == c.to_dict()


def test_describe():
    assert "3 constraint(s)" in _sched().describe()


# --- failure ---------------------------------------------------------------

def test_violations_aggregated_not_first_only():
    c = _sched()
    v = {"start": 18, "end": 9, "a": 90, "b": 90, "code1": "x", "code2": "x"}
    problems = c.violations(v)
    assert len(problems) == 3
    with pytest.raises(ContractError) as ei:
        c.validate_value(v)
    assert ei.value.details["code"] == "cross_field_violation"
    assert len(ei.value.details["violations"]) == 3


def test_field_validation_still_runs_first():
    v = _good()
    v["start"] = "nine"
    with pytest.raises(ContractError) as ei:
        _sched().validate_value(v)
    assert ei.value.details["code"] == "field_type_mismatch"


def test_type_mismatch_is_violation_not_crash():
    c = ConstrainedCompositeContract(
        contract_id="t",
        fields={"s": DecisionSpec(type="categorical", options=["a", "b"]),
                "n": DecisionSpec(type="numeric", minimum=0, maximum=10)},
        constraints=[FieldConstraint(("s",), "lt", {"field": "n"})])
    assert len(c.violations({"s": "a", "n": 5})) == 1


def test_non_numeric_sum_field_is_violation():
    c = FieldConstraint(("a", "b"), "sum_le", 10)
    assert c.check({"a": "x", "b": 1}) is not None


def test_missing_field_is_violation():
    c = FieldConstraint(("a",), "gt", 5)
    assert c.check({}) is not None


def test_unknown_field_in_constraint_rejected():
    with pytest.raises(ContractError):
        ConstrainedCompositeContract(
            contract_id="u",
            fields={"a": DecisionSpec(type="numeric", minimum=0,
                                      maximum=1)},
            constraints=[FieldConstraint(("zzz",), "gt", 0)])


def test_unknown_target_field_rejected():
    with pytest.raises(ContractError):
        ConstrainedCompositeContract(
            contract_id="u",
            fields={"a": DecisionSpec(type="numeric", minimum=0,
                                      maximum=1)},
            constraints=[FieldConstraint(("a",), "lt", {"field": "zzz"})])


def test_bad_op_rejected():
    with pytest.raises(ContractError):
        FieldConstraint(("a",), "roughly", 5)


def test_bad_arity_rejected():
    with pytest.raises(ContractError):
        FieldConstraint(("a", "b"), "lt", 5)
    with pytest.raises(ContractError):
        FieldConstraint(("a",), "all_distinct")


def test_missing_target_rejected():
    with pytest.raises(ContractError):
        FieldConstraint(("a",), "gt")


def test_non_numeric_sum_target_rejected():
    with pytest.raises(ContractError):
        FieldConstraint(("a", "b"), "sum_le", "lots")


def test_duplicate_constraint_fields_rejected():
    with pytest.raises(ContractError):
        FieldConstraint(("a", "a"), "all_distinct")


def test_constraint_from_dict_missing_key():
    with pytest.raises(ContractError):
        FieldConstraint.from_dict({"op": "gt"})


# --- boundary ----------------------------------------------------------------

def test_boundary_values_satisfy_le_ge():
    assert FieldConstraint(("a",), "le", 10).check({"a": 10}) is None
    assert FieldConstraint(("a",), "ge", 10).check({"a": 10}) is None
    assert FieldConstraint(("a",), "lt", 10).check({"a": 10}) is not None


def test_eq_ne_with_none_target():
    # None target must be explicit via {"field": ...} or literal; a bare
    # None is rejected at construction for comparison ops.
    with pytest.raises(ContractError):
        FieldConstraint(("a",), "eq", None)


def test_no_constraints_behaves_like_composite():
    c = ConstrainedCompositeContract(
        contract_id="plain",
        fields={"a": DecisionSpec(type="binary", statement="s")})
    c.validate_value({"a": "true"})
    assert c.violations({"a": "true"}) == []
