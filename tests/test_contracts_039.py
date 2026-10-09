"""Gjallarbrú slice 039 — risk matrices."""

from __future__ import annotations

import pytest

from hugrgate.contracts.cost import CostMatrix, min_cost_decision
from hugrgate.contracts.risk import (
    RiskContract,
    cvar_decision,
    cvar_of_decision,
    minimax_decision,
    minimax_regret_decision,
    regret_table,
)
from hugrgate.contracts.schema import contract_from_dict
from hugrgate.errors import ContractError

# calm: great usually, catastrophic in a crisis. crisis: steady.
COSTS = {
    "calm": {"calm": 0.0, "crisis": 100.0},
    "crisis": {"calm": 40.0, "crisis": 40.0},
}


def _m() -> CostMatrix:
    return CostMatrix(["calm", "crisis"], COSTS)


# --- success ---------------------------------------------------------------

def test_minimax_picks_robust():
    label, worst = minimax_decision(_m())
    assert (label, worst) == ("crisis", 40.0)


def test_minimax_differs_from_expectation():
    # p(calm)=0.9: E[calm]=10 < E[crisis]=40, but minimax still picks crisis.
    assert min_cost_decision(_m(), {"calm": 0.9, "crisis": 0.1})[0] == "calm"
    assert minimax_decision(_m())[0] == "crisis"


def test_regret_table():
    t = regret_table(_m())
    assert t["calm"] == {"calm": 0.0, "crisis": 60.0}
    assert t["crisis"] == {"calm": 40.0, "crisis": 0.0}
    assert all(v >= 0 for row in t.values() for v in row.values())


def test_minimax_regret():
    label, worst_regret = minimax_regret_decision(_m())
    assert (label, worst_regret) == ("crisis", 40.0)


def test_cvar_math():
    # losses {a: 10 @0.8, b: 100 @0.2}, alpha=0.9 -> tail 0.1 -> 100
    d2 = {"a": 0.8, "b": 0.2}
    m2 = CostMatrix(["a", "b"], {"a": {"a": 10.0, "b": 100.0},
                                 "b": {"a": 10.0, "b": 100.0}})
    assert cvar_of_decision(m2, d2, "a", 0.9) == pytest.approx(100.0)
    # alpha=0.5 -> tail 0.5: 0.2*100 + 0.3*10 = 23 -> 46
    assert cvar_of_decision(m2, d2, "a", 0.5) == pytest.approx(46.0)


def test_cvar_zero_is_expectation():
    d = {"calm": 0.9, "crisis": 0.1}
    assert cvar_of_decision(_m(), d, "calm", 0.0) == pytest.approx(10.0)


def test_cvar_decision():
    label, c = cvar_decision(_m(), {"calm": 0.9, "crisis": 0.1}, alpha=0.9)
    # tail 0.1: calm -> 100, crisis -> 40
    assert (label, c) == ("crisis", pytest.approx(40.0))


def test_contract_minimax_ignores_distribution():
    c = RiskContract(contract_id="r", outcomes=["calm", "crisis"],
                     costs=COSTS, attitude="minimax")
    assert c.decide() == ("crisis", 40.0)
    assert c.decide({"calm": 1.0, "crisis": 0.0}) == ("crisis", 40.0)


def test_contract_minimax_regret():
    c = RiskContract(contract_id="r", outcomes=["calm", "crisis"],
                     costs=COSTS, attitude="minimax_regret")
    assert c.decide()[0] == "crisis"


def test_contract_cvar():
    c = RiskContract(contract_id="r", outcomes=["calm", "crisis"],
                     costs=COSTS, attitude="cvar", cvar_alpha=0.9)
    label, _ = c.decide({"calm": 0.9, "crisis": 0.1})
    assert label == "crisis"
    with pytest.raises(ContractError):
        c.decide()  # cvar needs a distribution


def test_contract_expected_cost_baseline():
    c = RiskContract(contract_id="r", outcomes=["calm", "crisis"],
                     costs=COSTS)
    assert c.expected_cost({"calm": 0.9, "crisis": 0.1},
                           "calm") == pytest.approx(10.0)


def test_round_trip():
    c = RiskContract(contract_id="r", outcomes=["calm", "crisis"],
                     costs=COSTS, attitude="cvar", cvar_alpha=0.8)
    back = contract_from_dict(c.to_dict())
    assert back.to_dict() == c.to_dict()
    assert back.decide({"calm": 0.9, "crisis": 0.1}) == \
        c.decide({"calm": 0.9, "crisis": 0.1})


def test_describe():
    assert "attitude=minimax" in RiskContract(
        contract_id="r", outcomes=["calm", "crisis"],
        costs=COSTS).describe()


# --- failure ---------------------------------------------------------------

def test_bad_attitude_rejected():
    with pytest.raises(ContractError):
        RiskContract(contract_id="r", outcomes=["calm", "crisis"],
                     costs=COSTS, attitude="yolo")


def test_bad_alpha_rejected():
    with pytest.raises(ContractError):
        RiskContract(contract_id="r", outcomes=["calm", "crisis"],
                     costs=COSTS, attitude="cvar", cvar_alpha=1.0)
    with pytest.raises(ContractError):
        cvar_of_decision(_m(), {"calm": 0.5, "crisis": 0.5}, "calm", 1.5)


def test_unknown_decision_rejected():
    with pytest.raises(ContractError):
        cvar_of_decision(_m(), {"calm": 0.5, "crisis": 0.5}, "zzz", 0.9)


def test_validate_value():
    c = RiskContract(contract_id="r", outcomes=["calm", "crisis"],
                     costs=COSTS)
    c.validate_value("calm")
    with pytest.raises(ContractError):
        c.validate_value("zzz")


# --- boundary ----------------------------------------------------------------

def test_single_decision():
    m = CostMatrix(["only"], {"only": {"only": 7.0}})
    assert minimax_decision(m) == ("only", 7.0)
    assert minimax_regret_decision(m) == ("only", 0.0)


def test_minimax_tie_break():
    m = CostMatrix(["a", "b"], {"a": {"a": 3.0, "b": 3.0},
                                "b": {"a": 3.0, "b": 3.0}})
    assert minimax_decision(m) == ("a", 3.0)
