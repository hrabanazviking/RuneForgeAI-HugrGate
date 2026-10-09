"""Gjallarbrú slice 035 — distribution constraints."""

from __future__ import annotations

import math

import pytest

from hugrgate.contracts.distributions import (
    DistributionConstraint,
    DistributionContract,
    shannon_entropy,
)
from hugrgate.contracts.schema import contract_from_dict
from hugrgate.errors import ContractError


def _c() -> DistributionContract:
    return DistributionContract(
        contract_id="dx-1",
        outcomes=["a", "b", "c", "d"],
        constraints=[
            DistributionConstraint("min_top1", 0.5),
            DistributionConstraint("max_top1", 0.95),
            DistributionConstraint("min_margin", 0.1),
            DistributionConstraint("min_mass", 0.6, ("a", "b"),
                                   "a/b carry the mass"),
        ],
    )


# --- success ---------------------------------------------------------------

def test_entropy_math():
    assert shannon_entropy({"a": 1.0, "b": 0.0}) == pytest.approx(0.0)
    assert shannon_entropy({k: 0.25 for k in "abcd"}) == pytest.approx(
        math.log(4))


def test_healthy_distribution_passes():
    c = _c()
    d = {"a": 0.6, "b": 0.2, "c": 0.1, "d": 0.1}
    c.validate_distribution(d)
    assert c.distribution_violations(d) == []


def test_value_validation():
    c = _c()
    c.validate_value("b")
    with pytest.raises(ContractError):
        c.validate_value("zzz")


def test_min_entropy():
    con = DistributionConstraint("min_entropy", math.log(2))
    assert con.check({"a": 0.5, "b": 0.5}) is None
    assert con.check({"a": 1.0, "b": 0.0}) is not None


def test_max_entropy():
    con = DistributionConstraint("max_entropy", 0.5)
    assert con.check({"a": 0.9, "b": 0.1}) is None
    assert con.check({"a": 0.5, "b": 0.5}) is not None


def test_max_support():
    con = DistributionConstraint("max_support", 2)
    assert con.check({"a": 0.5, "b": 0.5, "c": 0.0}) is None
    assert con.check({"a": 0.4, "b": 0.3, "c": 0.3}) is not None


def test_min_mass():
    con = DistributionConstraint("min_mass", 0.6, ("a", "b"))
    assert con.check({"a": 0.5, "b": 0.2, "c": 0.3}) is None
    assert con.check({"a": 0.2, "b": 0.2, "c": 0.6}) is not None


def test_round_trip():
    c = _c()
    back = contract_from_dict(c.to_dict())
    assert isinstance(back, DistributionContract)
    assert back.to_dict() == c.to_dict()
    con = DistributionConstraint("min_mass", 0.6, ("a", "b"), "d")
    assert DistributionConstraint.from_dict(con.to_dict()).to_dict() == \
        con.to_dict()


def test_describe():
    assert "4 outcomes" in _c().describe()
    assert DistributionConstraint("min_top1", 0.7).describe() == \
        "min_top1(0.7)"


# --- failure ---------------------------------------------------------------

def test_overconfident_rejected():
    with pytest.raises(ContractError):
        _c().validate_distribution({"a": 1.0, "b": 0.0, "c": 0.0, "d": 0.0})


def test_indecisive_rejected():
    with pytest.raises(ContractError):
        _c().validate_distribution({k: 0.25 for k in "abcd"})


def test_violations_aggregated():
    c = _c()
    problems = c.distribution_violations({"a": 0.3, "b": 0.3, "c": 0.2,
                                          "d": 0.2})
    assert len(problems) >= 2  # min_top1 and min_margin both fail


def test_key_outside_outcomes():
    problems = _c().distribution_violations({"a": 0.6, "zzz": 0.4})
    assert any("outside outcomes" in p for p in problems)


def test_malformed_distribution_is_violation():
    con = DistributionConstraint("min_top1", 0.5)
    assert con.check({"a": 0.6, "b": 0.6}) is not None  # sums to 1.2
    assert con.check("nope") is not None
    assert con.check({}) is not None


def test_bad_op_rejected():
    with pytest.raises(ContractError):
        DistributionConstraint("vibes", 0.5)


def test_bad_thresholds_rejected():
    with pytest.raises(ContractError):
        DistributionConstraint("min_top1", 1.5)
    with pytest.raises(ContractError):
        DistributionConstraint("max_support", 2.5)
    with pytest.raises(ContractError):
        DistributionConstraint("max_support", 0)
    with pytest.raises(ContractError):
        DistributionConstraint("min_entropy", -1.0)


def test_min_mass_needs_labels():
    with pytest.raises(ContractError):
        DistributionConstraint("min_mass", 0.5)


def test_labels_with_wrong_op_rejected():
    with pytest.raises(ContractError):
        DistributionConstraint("min_top1", 0.5, ("a",))


def test_min_mass_unknown_label_rejected():
    with pytest.raises(ContractError):
        DistributionContract(
            contract_id="x", outcomes=["a", "b"],
            constraints=[DistributionConstraint("min_mass", 0.5, ("zzz",))])


def test_empty_outcomes_rejected():
    with pytest.raises(ContractError):
        DistributionContract(contract_id="x", outcomes=[])


def test_duplicate_outcomes_rejected():
    with pytest.raises(ContractError):
        DistributionContract(contract_id="x", outcomes=["a", "a"])


# --- boundary ----------------------------------------------------------------

def test_single_outcome():
    c = DistributionContract(contract_id="s", outcomes=["only"])
    c.validate_distribution({"only": 1.0})
    assert DistributionConstraint("min_margin", 0.5).check(
        {"only": 1.0}) is None  # margin vs implicit 0.0 second


def test_threshold_edges():
    assert DistributionConstraint("min_top1", 0.5).check(
        {"a": 0.5, "b": 0.5}) is None
    assert DistributionConstraint("max_top1", 0.5).check(
        {"a": 0.5, "b": 0.5}) is None
