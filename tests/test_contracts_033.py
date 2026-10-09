"""Gjallarbrú slice 033 — rich ordinal semantics."""

from __future__ import annotations

import pytest

from hugrgate.contracts.ordinal import OrdinalContract
from hugrgate.contracts.schema import contract_from_dict
from hugrgate.errors import ContractError


def _pain() -> OrdinalContract:
    return OrdinalContract(
        contract_id="pain-1",
        levels=["none", "mild", "moderate", "severe"],
        anchors={"none": 0.0, "mild": 2.0, "moderate": 5.0, "severe": 9.0},
    )


def _plain() -> OrdinalContract:
    return OrdinalContract(contract_id="plain", levels=["a", "b", "c"])


# --- success ---------------------------------------------------------------

def test_default_anchors_are_ranks():
    c = _plain()
    assert [c.anchor_of(lbl) for lbl in ("a", "b", "c")] == [0.0, 1.0, 2.0]


def test_custom_anchors():
    c = _pain()
    assert c.anchor_of("moderate") == 5.0
    assert c.distance("none", "severe") == 9.0
    assert c.distance("mild", "moderate") == 3.0


def test_rank_and_order():
    c = _pain()
    assert c.rank_of("none") == 0
    assert c.is_ordered("mild", "severe")
    assert not c.is_ordered("severe", "mild")
    assert c.is_ordered("mild", "mild")


def test_levels_between():
    assert _pain().levels_between("none", "severe") == ["mild", "moderate"]
    assert _pain().levels_between("severe", "none") == ["mild", "moderate"]
    assert _pain().levels_between("mild", "moderate") == []


def test_interpolate():
    c = _pain()
    assert c.interpolate(0.4) == "none"
    assert c.interpolate(8.9) == "severe"
    assert c.interpolate(100.0) == "severe"
    assert c.interpolate(-5.0) == "none"


def test_interpolate_tie_goes_lower():
    c = _pain()  # 3.5 is equidistant from mild@2 and moderate@5
    assert c.interpolate(3.5) == "mild"


def test_expected_anchor():
    c = _pain()
    got = c.expected_anchor({"none": 0.5, "mild": 0.5,
                             "moderate": 0.0, "severe": 0.0})
    assert got == pytest.approx(1.0)


def test_validate_value():
    c = _pain()
    c.validate_value("severe")
    assert c.check_value("extreme") != []


def test_validate_distribution_ok():
    _pain().validate_distribution({"none": 0.25, "mild": 0.25,
                                   "moderate": 0.25, "severe": 0.25})


def test_round_trip():
    c = _pain()
    back = contract_from_dict(c.to_dict())
    assert isinstance(back, OrdinalContract)
    assert back.to_dict() == c.to_dict()
    assert back.anchor_of("severe") == 9.0


def test_round_trip_default_anchors():
    back = contract_from_dict(_plain().to_dict())
    assert "anchors" not in back.to_dict()
    assert back.anchor_of("c") == 2.0


def test_describe():
    assert "4 levels" in _pain().describe()


# --- failure ---------------------------------------------------------------

def test_too_few_levels():
    with pytest.raises(ContractError):
        OrdinalContract(contract_id="x", levels=["only"])


def test_duplicate_levels():
    with pytest.raises(ContractError):
        OrdinalContract(contract_id="x", levels=["a", "a"])


def test_non_increasing_anchors_rejected():
    with pytest.raises(ContractError) as ei:
        OrdinalContract(contract_id="x", levels=["a", "b"],
                        anchors={"a": 5.0, "b": 5.0})
    assert ei.value.details["code"] == "anchors_not_increasing"


def test_decreasing_anchors_rejected():
    with pytest.raises(ContractError):
        OrdinalContract(contract_id="x", levels=["a", "b", "c"],
                        anchors={"a": 0.0, "b": 3.0, "c": 2.0})


def test_partial_anchors_rejected():
    with pytest.raises(ContractError):
        OrdinalContract(contract_id="x", levels=["a", "b"],
                        anchors={"a": 0.0})


def test_anchor_for_unknown_level_rejected():
    with pytest.raises(ContractError):
        OrdinalContract(contract_id="x", levels=["a", "b"],
                        anchors={"a": 0.0, "b": 1.0, "zzz": 2.0})


def test_non_numeric_anchor_rejected():
    with pytest.raises(ContractError):
        OrdinalContract(contract_id="x", levels=["a", "b"],
                        anchors={"a": 0.0, "b": "high"})


def test_unknown_level_rank():
    with pytest.raises(ContractError):
        _pain().rank_of("extreme")


def test_distribution_bad_key():
    with pytest.raises(ContractError):
        _pain().validate_distribution({"none": 0.5, "extreme": 0.5})


def test_distribution_not_normalized():
    with pytest.raises(ContractError):
        _pain().validate_distribution({"none": 0.5, "mild": 0.4})


def test_distribution_value_out_of_range():
    with pytest.raises(ContractError):
        _pain().validate_distribution({"none": 1.5, "mild": -0.5})


def test_interpolate_non_numeric():
    with pytest.raises(ContractError):
        _pain().interpolate("high")


# --- boundary ----------------------------------------------------------------

def test_single_gap_scale():
    c = OrdinalContract(contract_id="g", levels=["lo", "hi"],
                        anchors={"lo": -100.0, "hi": 100.0})
    assert c.distance("lo", "hi") == 200.0
    assert c.interpolate(0.0) == "lo"  # tie -> lower


def test_expected_anchor_degenerate():
    c = _plain()
    assert c.expected_anchor({"a": 0.0, "b": 0.0, "c": 1.0}) == 2.0
    with pytest.raises(ContractError):  # empty distribution cannot sum to 1
        c.expected_anchor({})
