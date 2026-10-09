"""Gjallarbrú slice 037 — cost-sensitive decisions."""

from __future__ import annotations

import pytest

from hugrgate.contracts.cost import (
    CostMatrix,
    CostSensitiveContract,
    expected_cost,
    min_cost_decision,
)
from hugrgate.contracts.schema import contract_from_dict
from hugrgate.errors import ContractError

OUTCOMES = ["legit", "fraud"]
COSTS = {
    "legit": {"legit": 0.0, "fraud": 100.0},   # missed fraud: expensive
    "fraud": {"legit": 10.0, "fraud": 0.0},    # false alarm: cheap
}


def _m() -> CostMatrix:
    return CostMatrix(OUTCOMES, COSTS)


def _c() -> CostSensitiveContract:
    return CostSensitiveContract(contract_id="fraud-1",
                                 outcomes=OUTCOMES, costs=COSTS)


# --- success ---------------------------------------------------------------

def test_expected_cost_math():
    m = _m()
    d = {"legit": 0.8, "fraud": 0.2}
    assert expected_cost(m, d, "legit") == pytest.approx(20.0)
    assert expected_cost(m, d, "fraud") == pytest.approx(8.0)


def test_min_cost_differs_from_max_prob():
    # p(legit)=0.8 is most likely, but flagging fraud is cheaper.
    label, cost = min_cost_decision(_m(), {"legit": 0.8, "fraud": 0.2})
    assert label == "fraud"
    assert cost == pytest.approx(8.0)


def test_min_cost_agrees_when_costs_symmetric():
    m = CostMatrix(["a", "b"], {"a": {"a": 0.0, "b": 1.0},
                                "b": {"a": 1.0, "b": 0.0}})
    label, _ = min_cost_decision(m, {"a": 0.7, "b": 0.3})
    assert label == "a"


def test_tie_break_is_outcome_order():
    m = CostMatrix(["a", "b"], {"a": {"a": 0.0, "b": 1.0},
                                "b": {"a": 1.0, "b": 0.0}})
    label, _ = min_cost_decision(m, {"a": 0.5, "b": 0.5})
    assert label == "a"


def test_contract_decide_and_regret():
    c = _c()
    label, cost = c.decide({"legit": 0.8, "fraud": 0.2})
    assert label == "fraud"
    assert c.regret({"legit": 0.8, "fraud": 0.2}, "legit") == \
        pytest.approx(12.0)
    assert c.regret({"legit": 0.8, "fraud": 0.2}, "fraud") == \
        pytest.approx(0.0)


def test_matrix_accessors():
    m = _m()
    assert m.outcomes == ("legit", "fraud")
    assert m.cost("legit", "fraud") == 100.0
    assert m.row("fraud") == {"legit": 10.0, "fraud": 0.0}
    assert m == CostMatrix.from_dict(m.to_dict())


def test_round_trip():
    c = _c()
    back = contract_from_dict(c.to_dict())
    assert isinstance(back, CostSensitiveContract)
    assert back.to_dict() == c.to_dict()
    assert back.decide({"legit": 0.8, "fraud": 0.2})[0] == "fraud"


def test_validate_value():
    c = _c()
    c.validate_value("fraud")
    with pytest.raises(ContractError):
        c.validate_value("maybe")


def test_nonzero_diagonal_allowed():
    m = CostMatrix(["a", "b"], {"a": {"a": 2.0, "b": 5.0},
                                "b": {"a": 5.0, "b": 3.0}})
    assert m.cost("a", "a") == 2.0


def test_describe():
    assert "2×2 cost matrix" in _c().describe()


# --- failure ---------------------------------------------------------------

def test_negative_cost_rejected():
    with pytest.raises(ContractError):
        CostMatrix(["a", "b"], {"a": {"a": 0.0, "b": -1.0},
                                "b": {"a": 1.0, "b": 0.0}})


def test_non_square_rejected():
    with pytest.raises(ContractError):
        CostMatrix(["a", "b"], {"a": {"a": 0.0, "b": 1.0},
                                "b": {"a": 1.0}})


def test_extra_row_rejected():
    with pytest.raises(ContractError):
        CostMatrix(["a"], {"a": {"a": 0.0}, "zzz": {"a": 1.0}})


def test_duplicate_outcomes_rejected():
    with pytest.raises(ContractError):
        CostMatrix(["a", "a"], {"a": {"a": 0.0}})


def test_unknown_pair_rejected():
    with pytest.raises(ContractError):
        _m().cost("legit", "zzz")


def test_distribution_outside_outcomes():
    with pytest.raises(ContractError):
        expected_cost(_m(), {"legit": 0.5, "zzz": 0.5}, "legit")


def test_unnormalized_distribution_rejected():
    with pytest.raises(ContractError):
        min_cost_decision(_m(), {"legit": 0.5, "fraud": 0.4})


def test_bool_cost_rejected():
    with pytest.raises(ContractError):
        CostMatrix(["a"], {"a": {"a": True}})


# --- boundary ----------------------------------------------------------------

def test_certain_distribution():
    label, cost = min_cost_decision(_m(), {"legit": 1.0, "fraud": 0.0})
    assert (label, cost) == ("legit", 0.0)


def test_zero_costs_everywhere():
    m = CostMatrix(["a", "b"], {"a": {"a": 0.0, "b": 0.0},
                                "b": {"a": 0.0, "b": 0.0}})
    label, cost = min_cost_decision(m, {"a": 0.3, "b": 0.7})
    assert (label, cost) == ("a", 0.0)  # tie -> outcome order
