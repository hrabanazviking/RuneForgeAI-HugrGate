"""Gjallarbrú slice 034 — numeric uncertainty intervals."""

from __future__ import annotations

import pytest

from hugrgate.contracts.schema import contract_from_dict
from hugrgate.contracts.uncertainty import (
    NumericIntervalContract,
    UncertainValue,
    coerce,
    contains,
    covers,
    intersect,
    widen,
    width,
)
from hugrgate.errors import ContractError


def _c() -> NumericIntervalContract:
    return NumericIntervalContract(
        contract_id="temp-1", minimum=-50.0, maximum=150.0,
        max_width=20.0, min_confidence=0.9)


def _v(**kw):
    d = {"estimate": 37.0, "lower": 36.0, "upper": 38.0, "confidence": 0.95}
    d.update(kw)
    return UncertainValue(**d)


# --- success ---------------------------------------------------------------

def test_uncertain_value_ok():
    v = _v()
    assert width(v) == 2.0
    assert contains(v, 37.0) and contains(v, 36.0) and not contains(v, 39.0)


def test_plain_number_coerces_to_point():
    v = coerce(37.5)
    assert (v.estimate, v.lower, v.upper, v.confidence) == (37.5, 37.5, 37.5, 1.0)
    assert width(v) == 0.0


def test_mapping_coerces():
    v = coerce({"estimate": 1.0, "lower": 0.0, "upper": 2.0})
    assert v.confidence == 0.95  # default


def test_contract_accepts_point_and_interval():
    c = _c()
    c.validate_value(37.0)
    c.validate_value(_v().to_dict())
    c.validate_value(_v())
    assert c.check_value(37.0) == []


def test_intersect_overlap():
    a, b = _v(), _v(estimate=37.5, lower=37.0, upper=39.0, confidence=0.99)
    i = intersect(a, b)
    assert i is not None
    assert (i.lower, i.upper) == (37.0, 38.0)
    assert i.confidence == 0.95  # conservative
    assert contains(i, i.estimate)


def test_intersect_disjoint_is_none():
    a = _v()
    b = _v(estimate=100.0, lower=99.0, upper=101.0)
    assert intersect(a, b) is None


def test_intersect_touching():
    a = _v()  # [36, 38]
    b = _v(estimate=39.0, lower=38.0, upper=40.0)
    i = intersect(a, b)
    assert i is not None and (i.lower, i.upper) == (38.0, 38.0)


def test_widen():
    v = _v()  # estimate 37, half-widths 1
    w = widen(v, 3.0)
    assert (w.lower, w.upper) == (34.0, 40.0)
    assert w.estimate == 37.0 and w.confidence == v.confidence
    assert width(widen(v, 0.0)) == 0.0


def test_covers():
    big = _v(estimate=37.0, lower=30.0, upper=40.0)
    assert covers(big, _v())
    assert not covers(_v(), big)


def test_round_trip():
    c = _c()
    back = contract_from_dict(c.to_dict())
    assert back.to_dict() == c.to_dict()
    back.validate_value(_v())
    v = UncertainValue.from_dict(_v().to_dict())
    assert v == _v()


def test_describe():
    assert "width ≤ 20" in _c().describe()


# --- failure ---------------------------------------------------------------

def test_inverted_interval_rejected():
    with pytest.raises(ContractError):
        UncertainValue(estimate=1.0, lower=2.0, upper=3.0)


def test_estimate_outside_interval_rejected():
    with pytest.raises(ContractError):
        UncertainValue(estimate=10.0, lower=0.0, upper=5.0)


def test_bad_confidence_rejected():
    for bad in (0.0, 1.5, -0.1):
        with pytest.raises(ContractError):
            UncertainValue(estimate=1.0, lower=0.0, upper=2.0,
                           confidence=bad)
    # 1.0 is valid: a degenerate certain point
    UncertainValue(estimate=1.0, lower=1.0, upper=1.0, confidence=1.0)


def test_non_numeric_rejected():
    with pytest.raises(ContractError):
        UncertainValue(estimate="x", lower=0.0, upper=1.0)


def test_estimate_out_of_range():
    with pytest.raises(ContractError) as ei:
        _c().validate_value(200.0)
    assert ei.value.details["code"] == "estimate_out_of_range"


def test_interval_exceeding_range():
    v = _v(estimate=140.0, lower=130.0, upper=160.0)
    with pytest.raises(ContractError) as ei:
        _c().validate_value(v)
    assert ei.value.details["code"] == "interval_out_of_range"


def test_too_wide_rejected():
    v = _v(lower=20.0, upper=60.0)  # width 40 > 20
    with pytest.raises(ContractError) as ei:
        _c().validate_value(v)
    assert ei.value.details["code"] == "interval_too_wide"


def test_low_confidence_rejected():
    v = _v(confidence=0.8)
    with pytest.raises(ContractError) as ei:
        _c().validate_value(v)
    assert ei.value.details["code"] == "confidence_too_low"


def test_bad_value_type():
    with pytest.raises(ContractError):
        _c().validate_value("hot")
    with pytest.raises(ContractError):
        coerce([1, 2])


def test_bad_bounds():
    with pytest.raises(ContractError):
        NumericIntervalContract(contract_id="b", minimum=10.0, maximum=10.0)
    with pytest.raises(ContractError):
        NumericIntervalContract(contract_id="b", minimum=5.0, maximum=1.0)


def test_bad_max_width():
    with pytest.raises(ContractError):
        NumericIntervalContract(contract_id="b", minimum=0.0, maximum=1.0,
                                max_width=-1.0)


def test_bad_widen_factor():
    with pytest.raises(ContractError):
        widen(_v(), -2.0)


def test_uncertain_from_dict_missing_key():
    with pytest.raises(ContractError):
        UncertainValue.from_dict({"estimate": 1.0})


# --- boundary ----------------------------------------------------------------

def test_zero_width_interval():
    v = UncertainValue.point(5.0)
    assert width(v) == 0.0 and contains(v, 5.0)
    NumericIntervalContract(contract_id="z", minimum=0.0, maximum=10.0,
                            max_width=0.0).validate_value(5.0)


def test_confidence_just_above_min():
    c = _c()
    c.validate_value(_v(confidence=0.9000001))


def test_bool_is_not_numeric():
    with pytest.raises(ContractError):
        UncertainValue(estimate=True, lower=0.0, upper=1.0)
