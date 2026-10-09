"""Slice 355 — Dataset split tooling.

Covers: shuffled/sequential/stratified splits, determinism under a
fixed seed, fraction validation (sum, positivity, duplicates,
empties), k-fold coverage/size/exhaustiveness, boundary errors
(empty input, k > n, k < 2), SplitPlan serialization, and sealed
per-split manifests.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import DatasetError
from hugrgate.evlab import (
    ColumnSpec,
    DatasetManifest,
    SplitPlan,
    kfold_indices,
    make_splits,
    manifest_splits,
)


def _items(n=100):
    return [{"state": {"x": i}, "group": "a" if i % 2 == 0 else "b",
             "expected": "y"}
            for i in range(n)]


# --- make_splits ---------------------------------------------------------------

def test_shuffled_split_sizes():
    subsets, _plan = make_splits(_items(100), seed=7)
    assert len(subsets["train"]) == 70
    assert len(subsets["validation"]) == 15
    assert len(subsets["test"]) == 15
    # Partition: every item exactly once.
    seen = [id(r) for part in subsets.values() for r in part]
    assert len(set(seen)) == 100


def test_sequential_preserves_order():
    subsets, _ = make_splits(_items(10), method="sequential",
                             splits=[("a", 0.5), ("b", 0.5)])
    assert [r["state"]["x"] for r in subsets["a"]] == list(range(5))
    assert [r["state"]["x"] for r in subsets["b"]] == list(range(5, 10))


def test_deterministic_under_seed():
    a, pa = make_splits(_items(50), seed=99)
    b, pb = make_splits(_items(50), seed=99)
    assert pa.to_dict() == pb.to_dict()
    for name in a:
        assert [r["state"]["x"] for r in a[name]] == \
               [r["state"]["x"] for r in b[name]]
    c, _ = make_splits(_items(50), seed=100)
    assert [r["state"]["x"] for r in c["train"]] != \
           [r["state"]["x"] for r in a["train"]]


def test_does_not_touch_global_rng_state():
    import random
    random.seed(1234)
    before = random.random()
    random.seed(1234)
    make_splits(_items(20), seed=5)
    assert random.random() == before


def test_stratified_preserves_group_mix():
    subsets, _ = make_splits(
        _items(100), seed=3, method="stratified", stratify_key="group")
    for _name, part in subsets.items():
        frac_a = sum(1 for r in part if r["group"] == "a") / len(part)
        assert frac_a == pytest.approx(0.5, abs=0.1)
    # All items still partitioned exactly once.
    assert sum(len(p) for p in subsets.values()) == 100


def test_stratified_needs_key():
    with pytest.raises(DatasetError):
        make_splits(_items(10), method="stratified")


def test_stratified_custom_key_fn():
    subsets, _ = make_splits(
        _items(20), method="stratified",
        key_fn=lambda r: r["state"]["x"] % 4,
        splits=[("a", 0.5), ("b", 0.5)])
    assert len(subsets["a"]) + len(subsets["b"]) == 20


def test_fraction_sum_rejected():
    with pytest.raises(DatasetError):
        make_splits(_items(10), splits=[("a", 0.6), ("b", 0.6)])


def test_nonpositive_fraction_rejected():
    with pytest.raises(DatasetError):
        make_splits(_items(10), splits=[("a", 1.0), ("b", 0.0)])


def test_duplicate_names_rejected():
    with pytest.raises(DatasetError):
        make_splits(_items(10), splits=[("a", 0.5), ("a", 0.5)])


def test_empty_items_rejected():
    with pytest.raises(DatasetError):
        make_splits([])


def test_bad_method_rejected():
    with pytest.raises(DatasetError):
        make_splits(_items(10), method="kmeans")


def test_single_split_takes_all():
    subsets, _ = make_splits(_items(7), splits=[("all", 1.0)])
    assert len(subsets["all"]) == 7


def test_plan_serialization_roundtrip():
    _, plan = make_splits(_items(30), seed=11, method="stratified",
                          stratify_key="group")
    clone = SplitPlan.from_dict(plan.to_dict())
    assert clone.to_dict() == plan.to_dict()
    # Re-deriving from the plan reproduces the split exactly.
    subsets2, _ = make_splits(
        _items(30),
        splits=clone.splits, seed=clone.seed, method=clone.method,
        stratify_key=clone.stratify_key)
    subsets1, _ = make_splits(
        _items(30), splits=plan.splits, seed=plan.seed,
        method=plan.method, stratify_key=plan.stratify_key)
    for name in subsets1:
        assert [r["state"]["x"] for r in subsets1[name]] == \
               [r["state"]["x"] for r in subsets2[name]]


# --- k-fold -----------------------------------------------------------------------

def test_kfold_coverage_and_sizes():
    folds = kfold_indices(10, k=5, seed=1)
    assert len(folds) == 5
    tested = []
    for train, test in folds:
        assert len(test) == 2
        assert len(train) == 8
        assert not set(train) & set(test)
        tested.extend(test)
    assert sorted(tested) == list(range(10))


def test_kfold_uneven_sizes_differ_by_one():
    folds = kfold_indices(10, k=3, seed=1)
    sizes = sorted(len(test) for _, test in folds)
    assert sizes == [3, 3, 4]


def test_kfold_deterministic():
    assert kfold_indices(20, 4, seed=42) == kfold_indices(20, 4, seed=42)
    assert kfold_indices(20, 4, seed=42) != kfold_indices(20, 4, seed=43)


def test_kfold_no_shuffle_is_contiguous():
    folds = kfold_indices(10, k=2, shuffle=False)
    assert folds[0][1] == list(range(5))
    assert folds[1][1] == list(range(5, 10))


def test_kfold_boundaries():
    with pytest.raises(DatasetError):
        kfold_indices(0, k=2)
    with pytest.raises(DatasetError):
        kfold_indices(10, k=1)
    with pytest.raises(DatasetError):
        kfold_indices(3, k=5)
    # k == n is legal (leave-one-out).
    assert len(kfold_indices(4, k=4)) == 4


# --- manifest_splits ---------------------------------------------------------------

def test_manifest_splits_seal_children():
    cols = [ColumnSpec(name="state", type="mapping", required=True),
            ColumnSpec(name="group", type="string", required=False),
            ColumnSpec(name="expected", type="any", required=False)]
    items = _items(40)
    manifest = DatasetManifest(name="parent", version="1.0.0",
                               columns=cols).seal(items)
    sealed, subsets, plan = manifest_splits(
        manifest, items, splits=[("train", 0.75), ("test", 0.25)],
        seed=21, method="stratified", stratify_key="group")
    assert set(sealed) == {"train", "test"}
    assert sealed["train"].name == "parent/train"
    assert len(subsets["train"]) == 30
    assert len(subsets["test"]) == 10
    # Each child verifies independently against its own items.
    sealed["train"].verify(subsets["train"])
    sealed["test"].verify(subsets["test"])
    with pytest.raises(DatasetError):
        sealed["train"].verify(subsets["test"])  # wrong items
    assert plan.method == "stratified"
    assert plan.input_fingerprint == manifest.fingerprint


def test_manifest_splits_requires_verified_parent():
    cols = [ColumnSpec(name="state", type="mapping", required=True)]
    manifest = DatasetManifest(name="p", version="1.0.0", columns=cols)
    items = [{"state": {}}]
    with pytest.raises(DatasetError):
        manifest_splits(manifest, items)  # parent never sealed
