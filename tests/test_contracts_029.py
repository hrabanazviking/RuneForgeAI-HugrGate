"""Gjallarbrú slice 029 — hierarchical labels."""

from __future__ import annotations

import pytest

from hugrgate.contracts.hierarchy import (
    HierarchicalLabelContract,
    LabelHierarchy,
    hierarchical_precision,
    hierarchical_recall,
)
from hugrgate.contracts.schema import contract_from_dict
from hugrgate.errors import ContractError

EDGES = [
    ("animal", "mammal"),
    ("animal", "bird"),
    ("mammal", "cat"),
    ("mammal", "dog"),
    ("cat", "siamese"),
    ("plant", "tree"),
]


def _h() -> LabelHierarchy:
    return LabelHierarchy.from_edges(EDGES)


def _c() -> HierarchicalLabelContract:
    return HierarchicalLabelContract(contract_id="h-1", edges=EDGES)


# --- success ---------------------------------------------------------------

def test_from_nested_matches_from_edges():
    h = LabelHierarchy.from_nested({
        "animal": {"mammal": {"cat": {"siamese": {}}, "dog": {}},
                   "bird": {}},
        "plant": {"tree": {}},
    })
    assert h.edges() == _h().edges()


def test_ancestors_root_to_parent():
    assert _h().ancestors("siamese") == ("animal", "mammal", "cat")
    assert _h().ancestors("animal") == ()


def test_descendants():
    assert _h().descendants("mammal") == frozenset({"cat", "dog", "siamese"})
    assert _h().descendants("siamese") == frozenset()


def test_roots_leaves_depth():
    h = _h()
    assert h.roots == ("animal", "plant")
    assert h.leaves == ("bird", "dog", "siamese", "tree")
    assert h.depth_of("animal") == 0
    assert h.depth_of("siamese") == 3
    assert len(h) == 8


def test_parent_children():
    h = _h()
    assert h.parent_of("cat") == "mammal"
    assert h.parent_of("animal") is None
    assert h.children_of("mammal") == ("cat", "dog")


def test_lca():
    h = _h()
    assert h.lowest_common_ancestor("siamese", "dog") == "mammal"
    assert h.lowest_common_ancestor("siamese", "siamese") == "siamese"
    assert h.lowest_common_ancestor("cat", "siamese") == "cat"
    assert h.lowest_common_ancestor("tree", "dog") is None  # separate trees


def test_close_adds_ancestors():
    assert _h().close(["siamese"]) == frozenset(
        {"siamese", "cat", "mammal", "animal"})
    assert _h().close([]) == frozenset()


def test_contains_and_len():
    h = _h()
    assert "dog" in h and "nope" not in h and 42 not in h


def test_contract_validates_label_sets():
    c = _c()
    c.validate_value(["siamese", "tree"])
    c.validate_value([])
    assert c.check_value(["siamese"]) == []


def test_contract_close_value():
    assert _c().close_value(["siamese"]) == frozenset(
        {"siamese", "cat", "mammal", "animal"})


def test_hierarchical_metrics_partial_credit():
    h = _h()
    # Predicted the parent instead of the exact leaf: partial credit.
    p = hierarchical_precision(["cat"], ["siamese"], h)
    r = hierarchical_recall(["cat"], ["siamese"], h)
    assert p == 1.0   # close({cat}) ⊆ close({siamese})
    assert r == 3 / 4  # 3 of 4 truth nodes recovered


def test_hierarchical_metrics_exact():
    h = _h()
    assert hierarchical_precision(["siamese"], ["siamese"], h) == 1.0
    assert hierarchical_recall(["siamese"], ["siamese"], h) == 1.0


def test_hierarchical_metrics_empty_edges():
    h = _h()
    assert hierarchical_precision([], ["siamese"], h) == 1.0
    assert hierarchical_recall(["siamese"], [], h) == 1.0


def test_round_trip():
    c = _c()
    back = contract_from_dict(c.to_dict())
    assert isinstance(back, HierarchicalLabelContract)
    assert back.to_dict() == c.to_dict()
    assert sorted(back.hierarchy.edges()) == sorted(EDGES)


def test_describe():
    assert "8 labels" in _c().describe()


# --- failure ---------------------------------------------------------------

def test_cycle_rejected():
    with pytest.raises(ContractError) as ei:
        LabelHierarchy.from_edges([("a", "b"), ("b", "a")])
    assert ei.value.details["code"] == "label_cycle"


def test_self_parent_rejected():
    with pytest.raises(ContractError):
        LabelHierarchy.from_edges([("a", "a")])


def test_multiple_parents_rejected():
    with pytest.raises(ContractError) as ei:
        LabelHierarchy.from_edges([("a", "c"), ("b", "c")])
    assert ei.value.details["code"] == "multiple_parents"


def test_unknown_label_in_value_rejected():
    with pytest.raises(ContractError) as ei:
        _c().validate_value(["siamese", "dragon"])
    assert ei.value.details["code"] == "unknown_label"


def test_duplicate_labels_rejected():
    with pytest.raises(ContractError):
        _c().validate_value(["cat", "cat"])


def test_string_value_rejected():
    with pytest.raises(ContractError):
        _c().validate_value("siamese")


def test_empty_hierarchy_rejected():
    with pytest.raises(ContractError):
        HierarchicalLabelContract(contract_id="e", edges=[])


def test_bad_edge_shape_rejected():
    with pytest.raises(ContractError):
        HierarchicalLabelContract(contract_id="e", edges=[("a",)])


def test_unknown_label_queries_raise():
    h = _h()
    for fn in (h.ancestors, h.descendants, h.depth_of, h.parent_of,
               h.children_of):
        with pytest.raises(ContractError):
            fn("nope")


# --- boundary ----------------------------------------------------------------

def test_single_node_hierarchy():
    h = LabelHierarchy.from_nested({"solo": {}})
    assert h.roots == ("solo",) and h.leaves == ("solo",) and len(h) == 1
    c = HierarchicalLabelContract(contract_id="s", edges=[], labels=["solo"])
    c.validate_value(["solo"])
    assert c.close_value(["solo"]) == frozenset({"solo"})
    back = contract_from_dict(c.to_dict())
    assert back.to_dict() == c.to_dict()
