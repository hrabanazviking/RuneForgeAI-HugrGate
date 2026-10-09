"""Gjallarbrú slice 044 — contract inheritance."""

from __future__ import annotations

import pytest

from hugrgate.contracts.inheritance import (
    DERIVED_FROM_KEY,
    derive_contract,
    is_compatible,
)
from hugrgate.contracts.multilabel import MultilabelContract
from hugrgate.contracts.nested import NestedCategoricalContract
from hugrgate.contracts.ordinal import OrdinalContract
from hugrgate.contracts.schema import DecisionContract, contract_from_dict
from hugrgate.contracts.uncertainty import NumericIntervalContract
from hugrgate.errors import ContractError
from hugrgate.spec import DecisionSpec


def _ord() -> OrdinalContract:
    return OrdinalContract(contract_id="base",
                           levels=["low", "medium", "high", "critical"])


# --- derive ---------------------------------------------------------------

def test_derive_overrides_fields():
    child = derive_contract(_ord(), "child-1", levels=["low", "high"],
                            name="triage-lite")
    assert child.levels == ["low", "high"]
    assert child.name == "triage-lite"
    assert child.kind == "ordinal"
    child.validate_value("low")
    with pytest.raises(ContractError):
        child.validate_value("medium")  # dropped level


def test_derive_records_provenance():
    base = _ord()
    child = derive_contract(base, "c2")
    assert child.metadata[DERIVED_FROM_KEY] == base.canonical_hash()


def test_derive_merges_metadata():
    base = OrdinalContract(contract_id="b", levels=["a", "b"],
                           metadata={"team": "x", "v": 1})
    child = derive_contract(base, "c", metadata={"v": 2, "extra": True})
    assert child.metadata["team"] == "x"
    assert child.metadata["v"] == 2
    assert child.metadata["extra"] is True


def test_derive_unknown_override_rejected():
    with pytest.raises(ContractError):
        derive_contract(_ord(), "c", levels2=["a"])


def test_derive_non_contract_rejected():
    with pytest.raises(ContractError):
        derive_contract(DecisionSpec(type="binary", statement="s"), "c")


def test_derive_invalid_child_rejected():
    with pytest.raises(ContractError):
        derive_contract(_ord(), "c", levels=["only-one"])


def test_derived_round_trips():
    child = derive_contract(_ord(), "c", levels=["low", "high"])
    back = contract_from_dict(child.to_dict())
    assert back.to_dict() == child.to_dict()


# --- compatibility ----------------------------------------------------------

def test_ordinal_narrowing_compatible():
    child = derive_contract(_ord(), "c", levels=["low", "high"])
    assert is_compatible(child, _ord())
    assert not is_compatible(_ord(), child)


def test_ordinal_reordered_incompatible():
    base = _ord()
    # Same levels, different order — not a valid ordinal derivation anyway,
    # but compatibility must reject order violations:
    other = OrdinalContract(contract_id="o", levels=["high", "low"])
    assert not is_compatible(other, base)


def test_ordinal_widening_incompatible():
    base = OrdinalContract(contract_id="b", levels=["low", "high"])
    wide = OrdinalContract(contract_id="w", levels=["low", "high", "extreme"])
    assert not is_compatible(wide, base)


def test_numeric_narrowing():
    base = NumericIntervalContract(contract_id="b", minimum=0.0,
                                   maximum=100.0)
    child = derive_contract(base, "c", minimum=10.0, maximum=90.0)
    assert is_compatible(child, base)
    assert not is_compatible(base, child)


def test_numeric_widened_confidence_incompatible():
    base = NumericIntervalContract(contract_id="b", minimum=0.0,
                                   maximum=1.0, min_confidence=0.9)
    loose = derive_contract(base, "c", min_confidence=0.5)
    assert not is_compatible(loose, base)


def test_multilabel_compatible():
    base = MultilabelContract(contract_id="b", labels=["a", "b", "c"],
                              min_count=1, required=["a"])
    child = derive_contract(base, "c", labels=["a", "b"], min_count=2)
    assert is_compatible(child, base)
    # loosening min_count accepts [] which the base rejects
    loose = derive_contract(base, "c2", min_count=0)
    assert not is_compatible(loose, base)


def test_nested_leaf_inclusion():
    base = NestedCategoricalContract(
        contract_id="b", options=["x", "y"],
        children={"x": NestedCategoricalContract(
            contract_id="bx", options=["x1", "x2"])})
    child = derive_contract(
        base, "c", children={"x": NestedCategoricalContract(
            contract_id="cx", options=["x1"])})
    assert is_compatible(child, base)
    assert not is_compatible(base, child)


def test_different_kinds_incompatible():
    assert not is_compatible(_ord(), DecisionContract(contract_id="b"))


def test_bad_args_raise():
    with pytest.raises(ContractError):
        is_compatible("nope", _ord())  # type: ignore[arg-type]


def test_identical_base_contracts_compatible():
    assert is_compatible(_ord(), _ord())


# --- boundary ----------------------------------------------------------------

def test_derive_chain_provenance():
    b = _ord()
    c1 = derive_contract(b, "c1", levels=["low", "medium", "high"])
    c2 = derive_contract(c1, "c2", levels=["low", "medium"])
    assert c2.metadata[DERIVED_FROM_KEY] == c1.canonical_hash()
    assert c1.metadata[DERIVED_FROM_KEY] == b.canonical_hash()
    assert is_compatible(c2, b)  # transitivity through narrowing


def test_derive_preserves_hash_stability():
    c1 = derive_contract(_ord(), "c", levels=["low", "high"])
    c2 = derive_contract(_ord(), "c", levels=["low", "high"])
    assert c1.canonical_hash() == c2.canonical_hash()
