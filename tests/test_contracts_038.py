"""Gjallarbrú slice 038 — utility matrices."""

from __future__ import annotations

import math

import pytest

from hugrgate.contracts.cost import min_cost_decision
from hugrgate.contracts.schema import contract_from_dict
from hugrgate.contracts.utility import (
    UtilityContract,
    UtilityMatrix,
    expected_utility,
    max_utility_decision,
)
from hugrgate.errors import ContractError

OUTCOMES = ["operate", "wait"]
# operate: big gain if needed, harm if not. wait: safe, small gain if needed.
UTILS = {
    "operate": {"operate": 50.0, "wait": -30.0},
    "wait": {"operate": 5.0, "wait": 0.0},
}


def _m() -> UtilityMatrix:
    return UtilityMatrix(OUTCOMES, UTILS)


def _c() -> UtilityContract:
    return UtilityContract(contract_id="tx-1", outcomes=OUTCOMES,
                           utilities=UTILS)


# --- success ---------------------------------------------------------------

def test_expected_utility_math():
    m = _m()
    d = {"operate": 0.6, "wait": 0.4}
    assert expected_utility(m, d, "operate") == pytest.approx(0.6 * 50 - 0.4 * 30)
    assert expected_utility(m, d, "wait") == pytest.approx(0.6 * 5)


def test_max_utility_decision():
    label, u = max_utility_decision(_m(), {"operate": 0.6, "wait": 0.4})
    assert label == "operate" and u == pytest.approx(18.0)
    label2, _ = max_utility_decision(_m(), {"operate": 0.1, "wait": 0.9})
    assert label2 == "wait"


def test_cost_utility_duality():
    # max-EU under U == min-cost under C = max(U) - U, on several distributions
    m = _m()
    c = m.as_cost_matrix()
    for d in ({"operate": 0.6, "wait": 0.4},
              {"operate": 0.1, "wait": 0.9},
              {"operate": 0.5, "wait": 0.5},
              {"operate": 1.0, "wait": 0.0}):
        assert max_utility_decision(m, d)[0] == min_cost_decision(c, d)[0]


def test_dual_costs_nonnegative():
    c = _m().as_cost_matrix()
    for dec in c.outcomes:
        for out in c.outcomes:
            assert c.cost(dec, out) >= 0.0


def test_contract_decide_and_regret():
    c = _c()
    label, u = c.decide({"operate": 0.6, "wait": 0.4})
    assert label == "operate"
    assert c.regret({"operate": 0.6, "wait": 0.4}, "wait") == \
        pytest.approx(u - 3.0)
    assert c.regret({"operate": 0.6, "wait": 0.4}, "operate") == \
        pytest.approx(0.0)


def test_matrix_round_trip():
    assert UtilityMatrix.from_dict(_m().to_dict()) == _m()


def test_contract_round_trip():
    back = contract_from_dict(_c().to_dict())
    assert isinstance(back, UtilityContract)
    assert back.to_dict() == _c().to_dict()


def test_validate_value():
    _c().validate_value("wait")
    with pytest.raises(ContractError):
        _c().validate_value("zzz")


def test_negative_utilities_allowed():
    assert _m().utility("operate", "wait") == -30.0


def test_describe():
    assert "2x2 utility matrix" in _c().describe()


# --- failure ---------------------------------------------------------------

def test_nan_rejected():
    with pytest.raises(ContractError):
        UtilityMatrix(["a"], {"a": {"a": math.nan}})


def test_inf_rejected():
    with pytest.raises(ContractError):
        UtilityMatrix(["a"], {"a": {"a": math.inf}})


def test_non_square_rejected():
    with pytest.raises(ContractError):
        UtilityMatrix(["a", "b"], {"a": {"a": 1.0, "b": 2.0},
                                   "b": {"a": 1.0}})


def test_bool_rejected():
    with pytest.raises(ContractError):
        UtilityMatrix(["a"], {"a": {"a": True}})


def test_unknown_pair():
    with pytest.raises(ContractError):
        _m().utility("operate", "zzz")


def test_bad_distribution():
    with pytest.raises(ContractError):
        expected_utility(_m(), {"operate": 0.5}, "operate")


# --- boundary ----------------------------------------------------------------

def test_all_equal_utilities():
    m = UtilityMatrix(["a", "b"], {"a": {"a": 1.0, "b": 1.0},
                                   "b": {"a": 1.0, "b": 1.0}})
    label, u = max_utility_decision(m, {"a": 0.2, "b": 0.8})
    assert (label, u) == ("a", 1.0)  # tie -> outcome order


def test_zero_utilities():
    m = UtilityMatrix(["a"], {"a": {"a": 0.0}})
    assert max_utility_decision(m, {"a": 1.0}) == ("a", 0.0)
