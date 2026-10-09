"""Gjallarbrú slice 030 — structured composite decisions."""

from __future__ import annotations

import pytest

from hugrgate.contracts.composite import CompositeContract
from hugrgate.contracts.hierarchy import HierarchicalLabelContract
from hugrgate.contracts.nested import NestedCategoricalContract
from hugrgate.contracts.schema import DecisionContract, contract_from_dict
from hugrgate.errors import ContractError
from hugrgate.spec import DecisionSpec


def _triage() -> CompositeContract:
    return CompositeContract(
        contract_id="triage-1",
        fields={
            "severity": DecisionSpec(type="ordinal",
                                     levels=["low", "medium", "high"]),
            "department": DecisionSpec(type="categorical",
                                       options=["er", "icu", "ward"]),
            "eta_minutes": DecisionSpec(type="numeric", minimum=0,
                                        maximum=240),
            "flags": DecisionSpec(type="multilabel",
                                  labels=["fall-risk", "allergy"]),
            "route": NestedCategoricalContract(
                contract_id="r", options=["a", "b"],
                children={"a": NestedCategoricalContract(
                    contract_id="r2", options=["a1", "a2"])}),
        },
    )


def _good_value():
    return {"severity": "high", "department": "er", "eta_minutes": 15,
            "flags": ["allergy"], "route": "a.a1"}


# --- success ---------------------------------------------------------------

def test_valid_structured_value():
    c = _triage()
    c.validate_value(_good_value())
    assert c.check_value(_good_value()) == []


def test_mixed_v1_v2_fields():
    c = _triage()
    assert isinstance(c.field_contract("severity"), DecisionSpec)
    assert isinstance(c.field_contract("route"), DecisionContract)


def test_nested_composite():
    inner = CompositeContract(contract_id="in",
                              fields={"x": DecisionSpec(type="binary",
                                                        statement="s")})
    outer = CompositeContract(contract_id="out",
                              fields={"inner": inner,
                                      "y": DecisionSpec(type="binary",
                                                        statement="t")})
    outer.validate_value({"inner": {"x": "true"}, "y": "false"})
    assert outer.check_value({"inner": {"x": "true"}, "y": "false"}) == []


def test_round_trip_mixed_fields():
    c = _triage()
    back = contract_from_dict(c.to_dict())
    assert isinstance(back, CompositeContract)
    assert back.to_dict() == c.to_dict()
    assert isinstance(back.field_contract("severity"), DecisionSpec)
    assert isinstance(back.field_contract("route"),
                      NestedCategoricalContract)
    back.validate_value(_good_value())


def test_bare_v1_spec_dict_accepted():
    c = CompositeContract(contract_id="b",
                          fields={"s": DecisionSpec(type="binary",
                                                    statement="q")})
    d = c.to_dict()
    d["fields"]["s"] = {"type": "binary", "statement": "q"}  # unwrapped
    back = contract_from_dict(d)
    assert isinstance(back.field_contract("s"), DecisionSpec)


def test_describe_lists_fields():
    s = _triage().describe()
    assert "5 fields" in s and "severity" in s


def test_field_names_and_lookup():
    c = _triage()
    assert c.field_names() == ["severity", "department", "eta_minutes",
                               "flags", "route"]
    with pytest.raises(ContractError):
        c.field_contract("nope")


# --- failure ---------------------------------------------------------------

def test_missing_field_rejected():
    v = _good_value()
    del v["eta_minutes"]
    with pytest.raises(ContractError) as ei:
        _triage().validate_value(v)
    assert ei.value.details["code"] == "missing_fields"


def test_unknown_field_rejected():
    v = _good_value()
    v["oops"] = 1
    with pytest.raises(ContractError) as ei:
        _triage().validate_value(v)
    assert ei.value.details["code"] == "unknown_fields"


def test_bad_scalar_field_value_rejected():
    v = _good_value()
    v["severity"] = "extreme"
    with pytest.raises(ContractError) as ei:
        _triage().validate_value(v)
    assert ei.value.details["code"] == "field_value_not_in_space"
    assert ei.value.details["field"] == "severity"


def test_bad_numeric_field_value_rejected():
    v = _good_value()
    v["eta_minutes"] = 999
    with pytest.raises(ContractError):
        _triage().validate_value(v)
    v["eta_minutes"] = "soon"
    with pytest.raises(ContractError):
        _triage().validate_value(v)


def test_bad_nested_field_value_rejected():
    v = _good_value()
    v["route"] = "a"  # ends at branch
    with pytest.raises(ContractError):
        _triage().validate_value(v)


def test_non_mapping_value_rejected():
    with pytest.raises(ContractError):
        _triage().validate_value("high")
    with pytest.raises(ContractError):
        _triage().validate_value(None)


def test_empty_fields_rejected():
    with pytest.raises(ContractError):
        CompositeContract(contract_id="e", fields={})


def test_bad_field_contract_type_rejected():
    with pytest.raises(ContractError):
        CompositeContract(contract_id="e", fields={"x": 42})


def test_bad_field_payload_rejected():
    d = _triage().to_dict()
    d["fields"]["severity"] = {"bogus": True}
    with pytest.raises(ContractError):
        contract_from_dict(d)


def test_hierarchical_field_inside_composite():
    c = CompositeContract(
        contract_id="h",
        fields={"dx": HierarchicalLabelContract(
            contract_id="dx",
            edges=[("a", "b"), ("a", "c")])})
    c.validate_value({"dx": ["b"]})
    with pytest.raises(ContractError):
        c.validate_value({"dx": ["zzz"]})


# --- boundary ----------------------------------------------------------------

def test_multilabel_field_empty_list_ok():
    v = _good_value()
    v["flags"] = []
    _triage().validate_value(v)


def test_numeric_bool_rejected():
    v = _good_value()
    v["eta_minutes"] = True
    with pytest.raises(ContractError):
        _triage().validate_value(v)


def test_error_chains_field_cause():
    v = _good_value()
    v["department"] = "morgue"
    with pytest.raises(ContractError) as ei:
        _triage().validate_value(v)
    assert "department" in ei.value.message
