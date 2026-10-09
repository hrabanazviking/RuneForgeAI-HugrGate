"""Gjallarbrú slice 036 — multilabel cardinality constraints."""

from __future__ import annotations

import pytest

from hugrgate.contracts.multilabel import MultilabelContract
from hugrgate.contracts.schema import contract_from_dict
from hugrgate.errors import ContractError


def _c() -> MultilabelContract:
    return MultilabelContract(
        contract_id="ml-1",
        labels=["a", "b", "c", "d", "e"],
        min_count=1,
        max_count=3,
        required=["a"],
        forbidden=["e"],
        implies={"b": ["c"]},
        excludes={"c": ["d"]},
    )


# --- success ---------------------------------------------------------------

def test_valid_selections():
    c = _c()
    c.validate_value(["a"])
    c.validate_value(["a", "b", "c"])  # b implies c: satisfied
    c.validate_value(["a", "d"])
    assert c.check_value(["a", "c"]) == []


def test_excludes_symmetrized():
    c = _c()
    assert "c" in c.excludes["d"] and "d" in c.excludes["c"]


def test_exact_count():
    c = MultilabelContract(contract_id="e", labels=["a", "b", "c"],
                           exact_count=2)
    c.validate_value(["a", "b"])
    with pytest.raises(ContractError):
        c.validate_value(["a"])
    assert "exactly 2" in c.describe()


def test_round_trip():
    c = _c()
    back = contract_from_dict(c.to_dict())
    assert isinstance(back, MultilabelContract)
    assert back.to_dict() == c.to_dict()
    back.validate_value(["a", "b", "c"])


def test_no_rules_is_plain_membership():
    c = MultilabelContract(contract_id="p", labels=["a", "b"])
    c.validate_value(["a", "b"])
    c.validate_value([])


# --- failure ---------------------------------------------------------------

def test_too_few():
    with pytest.raises(ContractError):
        _c().validate_value([])


def test_too_many():
    with pytest.raises(ContractError):
        _c().validate_value(["a", "b", "c", "d"])


def test_missing_required():
    with pytest.raises(ContractError) as ei:
        _c().validate_value(["b", "c"])
    assert any("required" in p for p in ei.value.details["violations"])


def test_forbidden_present():
    with pytest.raises(ContractError):
        _c().validate_value(["a", "e"])


def test_implies_violated():
    with pytest.raises(ContractError) as ei:
        _c().validate_value(["a", "b"])
    assert any("implies" in p for p in ei.value.details["violations"])


def test_excludes_violated():
    with pytest.raises(ContractError) as ei:
        _c().validate_value(["a", "c", "d"])
    assert any("excludes" in p for p in ei.value.details["violations"])


def test_violations_aggregated():
    c = _c()
    with pytest.raises(ContractError) as ei:
        c.validate_value(["b", "e", "x"])  # missing req, forbidden, unknown
    assert len(ei.value.details["violations"]) >= 3


def test_unknown_label():
    with pytest.raises(ContractError):
        _c().validate_value(["a", "zzz"])


def test_duplicate_labels():
    with pytest.raises(ContractError):
        _c().validate_value(["a", "a"])


def test_string_value_rejected():
    with pytest.raises(ContractError):
        _c().validate_value("a")


# --- construction guards -----------------------------------------------------

def test_max_lt_min_rejected():
    with pytest.raises(ContractError):
        MultilabelContract(contract_id="x", labels=["a", "b"],
                           min_count=2, max_count=1)


def test_required_forbidden_clash():
    with pytest.raises(ContractError):
        MultilabelContract(contract_id="x", labels=["a", "b"],
                           required=["a"], forbidden=["a"])


def test_rule_on_unknown_label():
    with pytest.raises(ContractError):
        MultilabelContract(contract_id="x", labels=["a"],
                           required=["zzz"])
    with pytest.raises(ContractError):
        MultilabelContract(contract_id="x", labels=["a"],
                           implies={"zzz": ["a"]})


def test_self_implies_rejected():
    with pytest.raises(ContractError):
        MultilabelContract(contract_id="x", labels=["a"],
                           implies={"a": ["a"]})


def test_required_excludes_required():
    with pytest.raises(ContractError):
        MultilabelContract(contract_id="x", labels=["a", "b"],
                           required=["a", "b"], excludes={"a": ["b"]})


def test_required_exceeds_exact():
    with pytest.raises(ContractError):
        MultilabelContract(contract_id="x", labels=["a", "b", "c"],
                           exact_count=1, required=["a", "b"])


def test_bad_counts():
    with pytest.raises(ContractError):
        MultilabelContract(contract_id="x", labels=["a"],
                           min_count=-1)
    with pytest.raises(ContractError):
        MultilabelContract(contract_id="x", labels=["a", "b"],
                           exact_count=5)


# --- boundary ----------------------------------------------------------------

def test_empty_selection_allowed_when_min_zero():
    MultilabelContract(contract_id="z", labels=["a"]).validate_value([])


def test_implies_chain():
    c = MultilabelContract(contract_id="ch", labels=["a", "b", "c"],
                           implies={"a": ["b"], "b": ["c"]})
    c.validate_value(["a", "b", "c"])
    with pytest.raises(ContractError):
        c.validate_value(["a", "b"])
