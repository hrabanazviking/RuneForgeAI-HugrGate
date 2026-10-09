"""Gjallarbrú slice 042 — input feature contracts."""

from __future__ import annotations

import pytest

from hugrgate.contracts.features import FeatureContract, FeatureSpec
from hugrgate.contracts.schema import contract_from_dict
from hugrgate.errors import ContractError


def _c() -> FeatureContract:
    return FeatureContract(
        contract_id="feat-1",
        features=[
            {"name": "age", "dtype": "int", "minimum": 0, "maximum": 120},
            {"name": "income", "dtype": "float", "minimum": 0.0},
            {"name": "vip", "dtype": "bool", "required": False,
             "default": False},
            {"name": "segment", "dtype": "category",
             "categories": ["a", "b", "c"]},
        ],
        allow_extra=False,
    )


# --- success ---------------------------------------------------------------

def test_valid_features():
    _c().validate_value({"age": 33, "income": 50000.0, "segment": "b"})
    assert _c().violations({"age": 33, "income": 1.0, "segment": "a",
                            "vip": True}) == []


def test_select_projects_and_orders():
    out = _c().select({"segment": "c", "income": 10.0, "age": 5})
    assert list(out) == ["age", "income", "vip", "segment"]  # declared order
    assert out["vip"] is False  # default filled


def test_select_drops_extras_when_allowed():
    c = FeatureContract(
        contract_id="x",
        features=[{"name": "a", "dtype": "float"}],
        allow_extra=True)
    assert c.select({"a": 1.0, "zzz": 2}) == {"a": 1.0}


def test_dtype_matrix():
    assert FeatureSpec("f", "float").check(1) is None        # int ok for float
    assert FeatureSpec("f", "float").check(True) is not None
    assert FeatureSpec("f", "int").check(3) is None
    assert FeatureSpec("f", "int").check(3.0) is not None
    assert FeatureSpec("f", "bool").check(False) is None
    assert FeatureSpec("f", "bool").check(0) is not None
    assert FeatureSpec("f", "category",
                       categories=("x",)).check("x") is None
    assert FeatureSpec("f", "category",
                       categories=("x",)).check("y") is not None


def test_round_trip():
    c = _c()
    back = contract_from_dict(c.to_dict())
    assert isinstance(back, FeatureContract)
    assert back.to_dict() == c.to_dict()
    assert back.feature_names() == ["age", "income", "vip", "segment"]


def test_spec_round_trip():
    s = FeatureSpec("age", "int", minimum=0, maximum=120)
    assert FeatureSpec.from_dict(s.to_dict()).to_dict() == s.to_dict()


def test_describe():
    assert "4 feature(s)" in _c().describe()


# --- failure ---------------------------------------------------------------

def test_missing_required():
    with pytest.raises(ContractError) as ei:
        _c().validate_value({"age": 1, "income": 1.0})
    assert ei.value.details["code"] == "feature_violation"


def test_out_of_range():
    problems = _c().violations({"age": 200, "income": 1.0, "segment": "a"})
    assert any("maximum" in p for p in problems)


def test_wrong_dtype():
    problems = _c().violations({"age": "old", "income": 1.0,
                                "segment": "a"})
    assert any("must be int" in p for p in problems)


def test_unknown_category():
    with pytest.raises(ContractError):
        _c().validate_value({"age": 1, "income": 1.0, "segment": "zzz"})


def test_extra_rejected():
    with pytest.raises(ContractError):
        _c().validate_value({"age": 1, "income": 1.0, "segment": "a",
                             "zzz": 1})


def test_violations_aggregated():
    problems = _c().violations({"income": "lots", "segment": "zzz",
                                "extra": 1})
    assert len(problems) >= 3  # missing age, bad income, bad segment


def test_non_mapping_rejected():
    with pytest.raises(ContractError):
        _c().validate_value([1, 2])


# --- construction guards -----------------------------------------------------

def test_empty_features_rejected():
    with pytest.raises(ContractError):
        FeatureContract(contract_id="x", features=[])


def test_duplicate_names_rejected():
    with pytest.raises(ContractError):
        FeatureContract(contract_id="x",
                        features=[{"name": "a"}, {"name": "a"}])


def test_bad_dtype_rejected():
    with pytest.raises(ContractError):
        FeatureSpec("x", "uuid")


def test_category_without_categories_rejected():
    with pytest.raises(ContractError):
        FeatureSpec("x", "category")


def test_range_on_category_rejected():
    with pytest.raises(ContractError):
        FeatureSpec("x", "category", categories=("a",), minimum=0)


def test_inverted_range_rejected():
    with pytest.raises(ContractError):
        FeatureSpec("x", "float", minimum=5, maximum=1)


def test_bad_default_rejected():
    with pytest.raises(ContractError):
        FeatureSpec("x", "int", required=False, default="nope")


def test_range_on_bool_rejected():
    with pytest.raises(ContractError):
        FeatureSpec("x", "bool", minimum=0)


# --- boundary ----------------------------------------------------------------

def test_boundary_values_ok():
    c = _c()
    c.validate_value({"age": 0, "income": 0.0, "segment": "a"})
    c.validate_value({"age": 120, "income": 1e18, "segment": "c"})


def test_none_default_allowed():
    c = FeatureContract(contract_id="x",
                        features=[{"name": "a", "dtype": "float",
                                   "required": False}])
    assert c.select({}) == {"a": None}
