"""Gjallarbrú slice 028 — nested categorical contracts."""

from __future__ import annotations

import pytest

from hugrgate.contracts.nested import (
    MAX_NESTING_DEPTH,
    NestedCategoricalContract,
    parse_path,
)
from hugrgate.contracts.schema import contract_from_dict
from hugrgate.errors import ContractError


def _tree() -> NestedCategoricalContract:
    return NestedCategoricalContract(
        contract_id="t-1",
        options=["animal", "plant"],
        children={
            "animal": NestedCategoricalContract(
                contract_id="t-1a",
                options=["mammal", "bird"],
                children={
                    "mammal": NestedCategoricalContract(
                        contract_id="t-1m", options=["dog", "cat"]),
                },
            ),
        },
    )


# --- success ---------------------------------------------------------------

def test_leaf_values_validate():
    t = _tree()
    t.validate_value("plant")
    t.validate_value(("plant",))
    t.validate_value(["plant"])


def test_deep_paths_validate_tuple_and_dotted():
    t = _tree()
    t.validate_value(("animal", "mammal", "dog"))
    t.validate_value("animal.mammal.cat")
    t.validate_value(("animal", "bird"))
    assert t.check_value("animal.bird") == []


def test_leaf_paths_enumerates_tree():
    assert _tree().leaf_paths() == [
        ("animal", "mammal", "dog"),
        ("animal", "mammal", "cat"),
        ("animal", "bird"),
        ("plant",),
    ]


def test_depth():
    assert _tree().depth() == 3
    assert NestedCategoricalContract(
        contract_id="s", options=["a", "b"]).depth() == 1


def test_subcontract_at():
    t = _tree()
    sub = t.subcontract_at(("animal", "mammal"))
    assert sub.options == ["dog", "cat"]
    assert t.subcontract_at("animal").options == ["mammal", "bird"]


def test_is_leaf():
    t = _tree()
    assert t.is_leaf("plant")
    assert not t.is_leaf("animal")


def test_round_trip_with_nested_children():
    t = _tree()
    back = contract_from_dict(t.to_dict())
    assert isinstance(back, NestedCategoricalContract)
    assert back.to_dict() == t.to_dict()
    assert back.leaf_paths() == t.leaf_paths()


def test_hash_stable_across_round_trip():
    t = _tree()
    assert contract_from_dict(t.to_dict()).canonical_hash() == t.canonical_hash()


def test_describe():
    assert "depth 3" in _tree().describe()


# --- failure ---------------------------------------------------------------

def test_unknown_option_rejected():
    with pytest.raises(ContractError):
        _tree().validate_value("animal.fish")


def test_trailing_segments_past_leaf_rejected():
    with pytest.raises(ContractError) as ei:
        _tree().validate_value("plant.extra")
    assert ei.value.details["code"] == "trailing_segments_at_leaf"


def test_path_ending_at_branch_rejected():
    with pytest.raises(ContractError) as ei:
        _tree().validate_value("animal.mammal")
    assert ei.value.details["code"] == "path_ends_at_branch"


def test_empty_options_rejected():
    with pytest.raises(ContractError):
        NestedCategoricalContract(contract_id="x", options=[])


def test_duplicate_options_rejected():
    with pytest.raises(ContractError):
        NestedCategoricalContract(contract_id="x", options=["a", "a"])


def test_dotted_option_rejected():
    with pytest.raises(ContractError):
        NestedCategoricalContract(contract_id="x", options=["a.b"])


def test_child_key_must_be_option():
    with pytest.raises(ContractError):
        NestedCategoricalContract(
            contract_id="x", options=["a"],
            children={"zzz": NestedCategoricalContract(
                contract_id="y", options=["b"])})


def test_child_must_be_nested_categorical():
    from hugrgate.contracts.schema import DecisionContract
    with pytest.raises(ContractError):
        NestedCategoricalContract(
            contract_id="x", options=["a"],
            children={"a": DecisionContract(contract_id="y")})


def test_wrong_kind_child_in_payload_rejected():
    d = _tree().to_dict()
    d["children"]["animal"] = {
        "schema_version": "2.0", "kind": "contract", "contract_id": "z"}
    with pytest.raises(ContractError):
        contract_from_dict(d)


def test_subcontract_at_leaf_raises():
    with pytest.raises(ContractError):
        _tree().subcontract_at("plant")


# --- boundary ----------------------------------------------------------------

def test_max_depth_guard():
    node = NestedCategoricalContract(contract_id="deep-0", options=["a"])
    for i in range(1, MAX_NESTING_DEPTH):
        node = NestedCategoricalContract(
            contract_id=f"deep-{i}", options=["a"], children={"a": node})
    assert node.depth() == MAX_NESTING_DEPTH  # exactly at the bound: OK
    # One more level trips the guard during the parent's __post_init__:
    with pytest.raises(ContractError) as ei:
        NestedCategoricalContract(
            contract_id="too-deep", options=["a"], children={"a": node})
    assert ei.value.details["code"] == "nesting_too_deep"


def test_exactly_max_depth_allowed():
    node = NestedCategoricalContract(contract_id="d0", options=["a"])
    for i in range(1, MAX_NESTING_DEPTH):
        node = NestedCategoricalContract(
            contract_id=f"d{i}", options=["a"], children={"a": node})
    assert node.depth() == MAX_NESTING_DEPTH


def test_bad_path_types():
    with pytest.raises(ContractError):
        parse_path(42)
    with pytest.raises(ContractError):
        parse_path("")
    with pytest.raises(ContractError):
        parse_path(("a", ""))
    with pytest.raises(ContractError):
        _tree().validate_value(None)


def test_single_option_tree():
    t = NestedCategoricalContract(contract_id="s", options=["only"])
    t.validate_value("only")
    assert t.leaf_paths() == [("only",)]
