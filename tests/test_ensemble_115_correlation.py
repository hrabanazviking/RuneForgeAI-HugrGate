"""Slice 115 — Correlated-error detection.

Members that err together are one model with extra latency. This
slice flags highly-correlated pairs (Q >= threshold) and merges them
into cliques.
"""

from __future__ import annotations

import pytest

from hugrgate.ensemble import (
    CorrelatedErrorReport,
    detect_correlated_errors,
)
from hugrgate.errors import PolicyError


# --- success -----------------------------------------------------------------

def test_identical_members_flagged_and_cliqued():
    hist = [True, True, False, True, False, False]
    report = detect_correlated_errors({"a": list(hist),
                                       "b": list(hist)})
    assert report.correlated is True
    assert len(report.pairs) == 1
    assert report.pairs[0].q == pytest.approx(1.0)
    assert report.cliques == [["a", "b"]]
    recs = report.recommendations()
    assert len(recs) == 1 and "a" in recs[0] and "b" in recs[0]


def test_independent_members_not_flagged():
    report = detect_correlated_errors({
        "a": [True, True, False, False],
        "b": [True, False, True, False],
        "c": [False, True, False, True],
    })
    assert report.correlated is False
    assert report.pairs == []
    assert report.cliques == []
    assert report.recommendations() == []


def test_partial_clique():
    # a and b identical; c independent -> one clique {a, b}
    hist = [True, False, True, False, True, False]
    report = detect_correlated_errors({
        "a": list(hist),
        "b": list(hist),
        "c": [True, True, False, False, False, True],
    })
    assert report.cliques == [["a", "b"]]
    assert report.members == ["a", "b", "c"]


def test_chained_correlation_forms_one_clique():
    # a~b (Q=0.6) and b~c (Q=0.6) flagged, a~c (Q=-0.6) not:
    # union-find still merges all three into one clique.
    a = [True, True, False, False, True, False]
    b = [True, True, False, False, False, True]
    c = [True, False, True, False, False, True]
    report = detect_correlated_errors({"a": a, "b": b, "c": c},
                                      threshold=0.5)
    flagged = {(p.member_a, p.member_b) for p in report.pairs}
    assert ("a", "b") in flagged
    assert ("b", "c") in flagged
    assert ("a", "c") not in flagged
    assert report.cliques == [["a", "b", "c"]]


def test_threshold_tunes_sensitivity():
    hist = [True, True, False, False]
    corr = {"a": list(hist), "b": list(hist)}
    assert detect_correlated_errors(corr,
                                    threshold=0.99).correlated is True
    # Q = 1.0 exactly; a threshold above 1.0 is rejected, so use
    # near-independent members for the negative case
    ind = {"a": [True, True, False, False],
           "b": [True, False, True, False]}
    assert detect_correlated_errors(ind, threshold=0.5).correlated \
        is False


def test_report_to_dict():
    hist = [True, False]
    report = detect_correlated_errors({"a": list(hist),
                                       "b": list(hist)})
    d = report.to_dict()
    assert d["correlated"] is True
    assert d["threshold"] == 0.7
    assert d["pairs"][0]["q"] == pytest.approx(1.0)
    assert isinstance(d["recommendations"], list)


# --- failure -----------------------------------------------------------------

def test_validation():
    with pytest.raises(PolicyError, match="at least 2 members"):
        detect_correlated_errors({"solo": [True]})
    with pytest.raises(PolicyError, match="in \\[-1, 1\\]"):
        detect_correlated_errors({"a": [True], "b": [True]},
                                 threshold=1.5)
    with pytest.raises(PolicyError, match="aligned"):
        detect_correlated_errors({"a": [True, False], "b": [True]})
    with pytest.raises(PolicyError, match="non-empty"):
        detect_correlated_errors({"a": [], "b": []})


# --- boundary -----------------------------------------------------------------

def test_pairs_sorted_by_q_descending():
    h1 = [True, True, False, False, True, False]
    h2 = [True, True, False, False, True, False]   # Q=1.0 with h1
    h3 = [True, False, True, False, True, False]
    report = detect_correlated_errors({"a": h1, "b": h2, "c": h3},
                                      threshold=0.0)
    qs = [p.q for p in report.pairs]
    assert qs == sorted(qs, reverse=True)
    assert report.pairs[0].q == pytest.approx(1.0)
