"""Slice 110 — Diversity metrics.

Pure-function metrics separating real ensembles from echo chambers:
label-free ballot statistics and labeled pairwise (in)dependence
measures.
"""

from __future__ import annotations

import math

import pytest

from hugrgate.ensemble import (
    disagreement_rate,
    diversity_summary,
    double_fault_rate,
    error_correlation,
    error_disagreement_rate,
    q_statistic,
    vote_entropy,
    winner_margin,
)
from hugrgate.ensemble.base import MemberVote
from hugrgate.errors import PolicyError

TWO = {"alpha": 0.6, "beta": 0.4}


def _v(name, value):
    return MemberVote(backend=name, value=value, probability=0.6,
                      distribution=dict(TWO))


# --- label-free ---------------------------------------------------------------

def test_vote_entropy_unanimous_is_zero():
    votes = [_v("a", "alpha"), _v("b", "alpha"), _v("c", "alpha")]
    assert vote_entropy(votes) == pytest.approx(0.0)


def test_vote_entropy_even_split_is_one_bit():
    votes = [_v("a", "alpha"), _v("b", "beta")]
    assert vote_entropy(votes) == pytest.approx(1.0)


def test_vote_entropy_partial_split():
    votes = [_v("a", "alpha"), _v("b", "alpha"), _v("c", "beta"),
             _v("d", "beta")]
    assert vote_entropy(votes) == pytest.approx(1.0)
    votes = [_v("a", "alpha"), _v("b", "alpha"), _v("c", "alpha"),
             _v("d", "beta")]
    # -(0.75*log2(0.75) + 0.25*log2(0.25))
    assert vote_entropy(votes) == pytest.approx(0.8112781)


def test_disagreement_rate():
    assert disagreement_rate([_v("a", "alpha")]) == 0.0
    votes = [_v("a", "alpha"), _v("b", "alpha"), _v("c", "beta")]
    # pairs: ab agree, ac/bc disagree -> 2/3
    assert disagreement_rate(votes) == pytest.approx(2 / 3)
    votes = [_v("a", "alpha"), _v("b", "beta")]
    assert disagreement_rate(votes) == pytest.approx(1.0)


def test_winner_margin():
    votes = [_v("a", "alpha"), _v("b", "alpha"), _v("c", "beta")]
    assert winner_margin(votes) == pytest.approx(2 / 3 - 1 / 3)
    votes = [_v("a", "alpha"), _v("b", "beta")]
    assert winner_margin(votes) == pytest.approx(0.0)
    votes = [_v("a", "alpha")]
    assert winner_margin(votes) == pytest.approx(1.0)


def test_skipped_votes_do_not_count():
    votes = [_v("a", "alpha"), _v("b", "beta")]
    votes[1].skipped = True
    assert vote_entropy(votes) == pytest.approx(0.0)
    assert disagreement_rate(votes) == pytest.approx(0.0)


def test_empty_ballots_rejected():
    with pytest.raises(PolicyError, match="at least one ballot"):
        vote_entropy([])
    with pytest.raises(PolicyError, match="at least one ballot"):
        winner_margin([])


def test_diversity_summary_keys():
    votes = [_v("a", "alpha"), _v("b", "beta")]
    s = diversity_summary(votes)
    assert s == {"vote_entropy_bits": pytest.approx(1.0),
                 "disagreement_rate": pytest.approx(1.0),
                 "winner_margin": pytest.approx(0.0),
                 "ballots": 2.0}


# --- labeled ------------------------------------------------------------------

def test_q_statistic_independent_errors():
    a = [True, True, False, False]
    b = [True, False, True, False]
    # N11=N10=N01=N00=1 -> (1-1)/(1+1) = 0
    assert q_statistic(a, b) == pytest.approx(0.0)


def test_q_statistic_identical_members():
    a = [True, True, False, False]
    assert q_statistic(a, list(a)) == pytest.approx(1.0)


def test_q_statistic_complementary_members():
    a = [True, False, True, False]
    b = [False, True, False, True]
    assert q_statistic(a, b) == pytest.approx(-1.0)


def test_q_statistic_degenerate_returns_neutral():
    assert q_statistic([True, True], [True, True]) == 0.0
    with pytest.raises(PolicyError, match="non-empty"):
        q_statistic([], [])
    with pytest.raises(PolicyError, match="disagree in length"):
        q_statistic([True], [True, False])


def test_double_fault_rate():
    assert double_fault_rate([True, False], [True, False]) == \
        pytest.approx(0.5)
    assert double_fault_rate([True, True], [True, True]) == \
        pytest.approx(0.0)
    with pytest.raises(PolicyError, match="disagree in length"):
        double_fault_rate([True], [])


def test_error_disagreement_rate():
    a = [True, True, False, False]
    b = [True, False, False, True]
    assert error_disagreement_rate(a, b) == pytest.approx(0.5)
    with pytest.raises(PolicyError, match="non-empty"):
        error_disagreement_rate([], [])


def test_error_correlation():
    assert error_correlation([0.1, 0.9], [0.1, 0.9]) == \
        pytest.approx(1.0)
    assert error_correlation([0.1, 0.9], [0.9, 0.1]) == \
        pytest.approx(-1.0)
    # zero variance -> neutral 0.0, not a crash
    assert error_correlation([0.5, 0.5], [0.1, 0.9]) == 0.0
    with pytest.raises(PolicyError, match="disagree in length"):
        error_correlation([0.1], [0.1, 0.2])
    with pytest.raises(PolicyError, match="needs data"):
        error_correlation([], [])


def test_q_statistic_partial_hand_computation():
    # a right 3/4, b right 3/4, overlap on 2: N11=2 N10=1 N01=1 N00=0
    a = [True, True, True, False]
    b = [True, True, False, True]
    # (2*0 - 1*1)/(2*0 + 1*1) = -1
    assert q_statistic(a, b) == pytest.approx(-1.0)
    assert math.isclose(q_statistic(a, b), -1.0)
