"""Gjallarbrú slice 040 — decision deadlines."""

from __future__ import annotations

import pytest

from hugrgate.contracts.deadlines import TimedContract
from hugrgate.contracts.ordinal import OrdinalContract
from hugrgate.contracts.schema import contract_from_dict
from hugrgate.errors import ContractError
from hugrgate.spec import DecisionSpec

T0 = 1_700_000_000.0  # fixed clock for deterministic tests


def _c(**kw) -> TimedContract:
    d = {"inner": DecisionSpec(type="binary", statement="launch?"),
         "budget_ms": 500.0}
    d.update(kw)
    return TimedContract(contract_id="t-1", **d)


# --- success ---------------------------------------------------------------

def test_in_budget():
    c = _c()
    c.check_timing(T0, T0 + 0.25)  # 250ms < 500ms
    assert c.timing_violations(T0, T0 + 0.25) == []


def test_value_delegates_to_inner():
    c = _c()
    c.validate_value("true")
    with pytest.raises(ContractError):
        c.validate_value("maybe")


def test_value_delegates_to_v2_inner():
    c = TimedContract(
        contract_id="t2",
        inner=OrdinalContract(contract_id="o", levels=["lo", "hi"]),
        budget_ms=100.0)
    c.validate_value("hi")
    with pytest.raises(ContractError):
        c.validate_value("mid")


def test_window_ok():
    c = _c(not_before=T0, not_after=T0 + 3600, budget_ms=None)
    c.check_timing(T0 + 10, T0 + 20)
    assert c.is_valid_at(T0 + 100)
    assert not c.is_valid_at(T0 + 7200)
    assert not c.is_valid_at(T0 - 10)


def test_remaining_budget():
    c = _c()
    assert c.remaining_budget_ms(T0, T0 + 0.1) == pytest.approx(400.0)
    assert c.remaining_budget_ms(T0, T0 + 1.0) == pytest.approx(-500.0)
    assert _c(budget_ms=None, not_before=T0,
              not_after=T0 + 10).remaining_budget_ms(T0, T0) is None


def test_round_trip():
    c = _c(not_before=T0, not_after=T0 + 60)
    back = contract_from_dict(c.to_dict())
    assert isinstance(back, TimedContract)
    assert back.to_dict() == c.to_dict()
    back.check_timing(T0, T0 + 0.1)


def test_round_trip_v2_inner():
    c = TimedContract(
        contract_id="t2",
        inner=OrdinalContract(contract_id="o", levels=["lo", "hi"]),
        budget_ms=100.0)
    back = contract_from_dict(c.to_dict())
    assert isinstance(back.inner, OrdinalContract)


def test_describe():
    assert "budget 500ms" in _c().describe()


# --- failure ---------------------------------------------------------------

def test_over_budget():
    with pytest.raises(ContractError) as ei:
        _c().check_timing(T0, T0 + 0.75)
    assert ei.value.details["code"] == "deadline_violation"


def test_decided_before_request():
    problems = _c().timing_violations(T0, T0 - 1)
    assert any("precedes" in p for p in problems)


def test_outside_window():
    c = _c(not_before=T0 + 100, not_after=T0 + 200, budget_ms=None)
    assert len(c.timing_violations(T0, T0 + 10)) == 1  # before not_before
    assert len(c.timing_violations(T0, T0 + 300)) == 1  # after not_after


def test_violations_aggregated():
    c = _c(budget_ms=100.0, not_after=T0 + 0.05)
    problems = c.timing_violations(T0, T0 + 0.5)
    assert len(problems) == 2  # over budget AND past not_after


def test_no_temporal_bound_rejected():
    with pytest.raises(ContractError):
        TimedContract(contract_id="x",
                      inner=DecisionSpec(type="binary", statement="s"))


def test_bad_budget_rejected():
    with pytest.raises(ContractError):
        TimedContract(contract_id="x",
                      inner=DecisionSpec(type="binary", statement="s"),
                      budget_ms=0)
    with pytest.raises(ContractError):
        TimedContract(contract_id="x",
                      inner=DecisionSpec(type="binary", statement="s"),
                      budget_ms=-5)


def test_inverted_window_rejected():
    with pytest.raises(ContractError):
        TimedContract(contract_id="x",
                      inner=DecisionSpec(type="binary", statement="s"),
                      not_before=T0 + 10, not_after=T0)


def test_bad_inner_rejected():
    with pytest.raises(ContractError):
        TimedContract(contract_id="x", inner="nope", budget_ms=10)


def test_missing_inner_in_payload():
    d = _c().to_dict()
    del d["inner"]
    with pytest.raises(ContractError):
        contract_from_dict(d)


# --- boundary ----------------------------------------------------------------

def test_exactly_at_budget_ok():
    _c().check_timing(T0, T0 + 0.5)  # exactly 500ms: not over


def test_exactly_at_window_edges_ok():
    c = _c(not_before=T0, not_after=T0 + 10, budget_ms=None)
    c.check_timing(T0, T0)
    c.check_timing(T0, T0 + 10)
    assert c.is_valid_at(T0) and c.is_valid_at(T0 + 10)
