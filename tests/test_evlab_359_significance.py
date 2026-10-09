"""Slice 359 — Significance testing.

Covers: permutation test significance/non-significance, one-sided
alternatives, determinism, McNemar exact p-values (known cases),
validation errors, paired-correctness comparison end-to-end, and
serialization round-trip.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import EvalError
from hugrgate.evlab import (
    SignificanceResult,
    compare_paired_correctness,
    mcnemar_test,
    paired_permutation_test,
)
from hugrgate.result import DecisionResult


def _result(value, prob=0.9):
    return DecisionResult(value=value, probability=prob,
                          distribution={"a": prob if value == "a" else 1 - prob,
                                        "b": prob if value == "b" else 1 - prob})


# --- permutation ------------------------------------------------------------------

def test_permutation_detects_real_difference():
    a = [1.0] * 40
    b = [0.0] * 40
    res = paired_permutation_test(a, b, n_perm=2000, seed=1)
    assert res.significant
    assert res.p_value < 0.01
    assert res.statistic == pytest.approx(1.0)
    assert res.details["mean_difference"] == pytest.approx(1.0)
    assert res.verdict == "significant"


def test_permutation_no_difference():
    rng_a = [1.0, 0.0] * 25
    rng_b = [1.0, 0.0] * 25
    res = paired_permutation_test(rng_a, rng_b, n_perm=2000, seed=2)
    assert not res.significant
    assert res.p_value == pytest.approx(1.0)
    assert res.verdict == "not significant"


def test_permutation_one_sided():
    a = [1.0] * 30
    b = [0.0] * 30
    greater = paired_permutation_test(a, b, n_perm=2000, seed=3,
                                      alternative="greater")
    less = paired_permutation_test(a, b, n_perm=2000, seed=3,
                                   alternative="less")
    assert greater.significant
    assert not less.significant


def test_permutation_deterministic():
    a = [1.0] * 25 + [0.0] * 25
    b = [0.0] * 25 + [1.0] * 25
    r1 = paired_permutation_test(a, b, n_perm=2000, seed=7)
    r2 = paired_permutation_test(a, b, n_perm=2000, seed=7)
    assert r1.to_dict() == r2.to_dict()


def test_permutation_validation():
    with pytest.raises(EvalError):
        paired_permutation_test([1.0], [1.0, 0.0])
    with pytest.raises(EvalError):
        paired_permutation_test([1.0], [0.0])
    with pytest.raises(EvalError):
        paired_permutation_test([1.0, float("nan")], [0.0, 1.0])
    with pytest.raises(EvalError):
        paired_permutation_test([1.0, 0.0], [0.0, 1.0], n_perm=100)
    with pytest.raises(EvalError):
        paired_permutation_test([1.0, 0.0], [0.0, 1.0],
                                alternative="sideways")
    with pytest.raises(EvalError):
        paired_permutation_test([1.0, 0.0], [0.0, 1.0], alpha=2.0)


def test_result_roundtrip():
    res = paired_permutation_test([1.0, 1.0, 0.0], [0.0, 1.0, 0.0],
                                  n_perm=1000, seed=5)
    assert SignificanceResult.from_dict(res.to_dict()).to_dict() == \
        res.to_dict()


# --- McNemar ------------------------------------------------------------------------

def test_mcnemar_known_significant():
    # 10 vs 2 discordant: exact two-sided p ~ 0.039.
    res = mcnemar_test(10, 2)
    assert res.significant
    assert res.p_value == pytest.approx(0.0386, abs=1e-3)
    assert res.details["b01"] == 10


def test_mcnemar_balanced_not_significant():
    res = mcnemar_test(6, 6)
    assert not res.significant
    assert res.p_value == pytest.approx(1.0)


def test_mcnemar_no_discordant_rejected():
    with pytest.raises(EvalError):
        mcnemar_test(0, 0)


def test_mcnemar_validation():
    with pytest.raises(EvalError):
        mcnemar_test(-1, 2)
    with pytest.raises(EvalError):
        mcnemar_test(1.5, 2)


# --- paired correctness comparison ------------------------------------------------------

def test_compare_paired_correctness_end_to_end():
    # A is always right, B is always wrong, over 30 items.
    pairs_a = [("a", _result("a")) for _ in range(30)]
    pairs_b = [("a", _result("b")) for _ in range(30)]
    report = compare_paired_correctness(
        pairs_a, pairs_b, n_perm=2000, seed=11,
        label_a="good", label_b="bad")
    assert report["accuracy_a"] == pytest.approx(1.0)
    assert report["accuracy_b"] == pytest.approx(0.0)
    assert report["n_items"] == 30
    assert report["mcnemar"]["significant"] is True
    assert report["permutation"]["significant"] is True


def test_compare_skips_abstentions_pairwise():
    pairs_a = [("a", _result("a")), ("a", None), ("b", _result("b"))]
    pairs_b = [("a", _result("a")), ("a", _result("a")), ("b", None)]
    # Only the first item is jointly scored -> too few.
    with pytest.raises(EvalError):
        compare_paired_correctness(pairs_a, pairs_b)


def test_compare_length_mismatch_rejected():
    with pytest.raises(EvalError):
        compare_paired_correctness([("a", _result("a"))], [])
