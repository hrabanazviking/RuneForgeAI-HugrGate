"""Diversity metrics — measuring *useful* disagreement. Slice 110.

An ensemble of clones is a single model with extra latency.
Diversity metrics quantify how differently members behave, so
operators can tell a real ensemble from an echo chamber:

Label-free (one decision, from ballots):
- :func:`vote_entropy` — entropy (bits) of the ballot distribution;
- :func:`disagreement_rate` — fraction of member pairs casting
  different ballots;
- :func:`winner_margin` — winner's hard-vote share minus the
  runner-up's.

Labeled (histories of correctness / probability-for-truth):
- :func:`q_statistic` — classic pairwise Q in [-1, 1] (0 =
  independent errors, 1 = identical, -1 = perfectly complementary);
- :func:`double_fault_rate` — fraction of samples both members miss;
- :func:`error_disagreement_rate` — fraction exactly one misses;
- :func:`error_correlation` — Pearson correlation of the members'
  probability-for-truth vectors.

All functions are pure and deterministic. Degenerate inputs (zero
variance, empty histories) return documented neutral values rather
than raising — a metric that crashes on unanimous members is worse
than useless.
"""

from __future__ import annotations

import math

from hugrgate.ensemble.base import MemberVote, shannon_entropy
from hugrgate.errors import PolicyError

__all__ = [
    "disagreement_rate",
    "diversity_summary",
    "double_fault_rate",
    "error_correlation",
    "error_disagreement_rate",
    "q_statistic",
    "vote_entropy",
    "winner_margin",
]


def _ballot_values(votes: list[MemberVote]) -> list[str]:
    return [str(v.value) for v in votes
            if not v.skipped and v.value is not None]


def vote_entropy(votes: list[MemberVote]) -> float:
    """Entropy (bits) of the ballot distribution.

    0 = unanimous; log2(#distinct ballots) = maximally split.
    """
    values = _ballot_values(votes)
    if not values:
        raise PolicyError("vote_entropy needs at least one ballot")
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    n = len(values)
    return shannon_entropy({k: c / n for k, c in counts.items()})


def disagreement_rate(votes: list[MemberVote]) -> float:
    """Fraction of member pairs casting different ballots."""
    values = _ballot_values(votes)
    n = len(values)
    if n < 2:
        return 0.0
    disagree = sum(1 for i in range(n) for j in range(i + 1, n)
                   if values[i] != values[j])
    return disagree / (n * (n - 1) / 2)


def winner_margin(votes: list[MemberVote]) -> float:
    """Winner's ballot share minus the runner-up's (0 when tied)."""
    values = _ballot_values(votes)
    if not values:
        raise PolicyError("winner_margin needs at least one ballot")
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    shares = sorted((c / len(values) for c in counts.values()),
                    reverse=True)
    return shares[0] - (shares[1] if len(shares) > 1 else 0.0)


def q_statistic(correct_a: list[bool],
                correct_b: list[bool]) -> float:
    """Pairwise Q statistic in [-1, 1].

    ``(N11*N00 - N01*N10) / (N11*N00 + N01*N10)`` where N11 = both
    right, N00 = both wrong, N01/N10 = exactly one right. Returns 0.0
    when the denominator is 0 (no evidence of (in)dependence, e.g.
    both members never err).
    """
    if len(correct_a) != len(correct_b):
        raise PolicyError(
            f"histories disagree in length: {len(correct_a)} vs "
            f"{len(correct_b)}")
    if not correct_a:
        raise PolicyError("q_statistic needs a non-empty history")
    n11 = n00 = n01 = n10 = 0
    for a, b in zip(correct_a, correct_b, strict=True):
        if a and b:
            n11 += 1
        elif not a and not b:
            n00 += 1
        elif b:
            n01 += 1
        else:
            n10 += 1
    denom = n11 * n00 + n01 * n10
    if denom == 0:
        return 0.0
    return (n11 * n00 - n01 * n10) / denom


def double_fault_rate(correct_a: list[bool],
                      correct_b: list[bool]) -> float:
    """Fraction of samples both members get wrong."""
    if len(correct_a) != len(correct_b):
        raise PolicyError(
            f"histories disagree in length: {len(correct_a)} vs "
            f"{len(correct_b)}")
    if not correct_a:
        raise PolicyError("double_fault_rate needs a non-empty history")
    both_wrong = sum(1 for a, b in zip(correct_a, correct_b, strict=True)
                     if not a and not b)
    return both_wrong / len(correct_a)


def error_disagreement_rate(correct_a: list[bool],
                            correct_b: list[bool]) -> float:
    """Fraction of samples exactly one member gets wrong."""
    if len(correct_a) != len(correct_b):
        raise PolicyError(
            f"histories disagree in length: {len(correct_a)} vs "
            f"{len(correct_b)}")
    if not correct_a:
        raise PolicyError(
            "error_disagreement_rate needs a non-empty history")
    split = sum(1 for a, b in zip(correct_a, correct_b, strict=True) if a != b)
    return split / len(correct_a)


def error_correlation(probs_a: list[float],
                      probs_b: list[float]) -> float:
    """Pearson correlation of probability-for-truth vectors.

    Returns 0.0 when either vector has zero variance (no signal to
    correlate).
    """
    if len(probs_a) != len(probs_b):
        raise PolicyError(
            f"vectors disagree in length: {len(probs_a)} vs "
            f"{len(probs_b)}")
    n = len(probs_a)
    if n == 0:
        raise PolicyError("error_correlation needs data")
    ma = sum(probs_a) / n
    mb = sum(probs_b) / n
    cov = sum((a - ma) * (b - mb) for a, b in zip(probs_a, probs_b, strict=True))
    va = sum((a - ma) ** 2 for a in probs_a)
    vb = sum((b - mb) ** 2 for b in probs_b)
    if va <= 0 or vb <= 0:
        return 0.0
    return cov / math.sqrt(va * vb)


def diversity_summary(votes: list[MemberVote]) -> dict[str, float]:
    """One-call label-free diversity snapshot for a decision."""
    return {
        "vote_entropy_bits": vote_entropy(votes),
        "disagreement_rate": disagreement_rate(votes),
        "winner_margin": winner_margin(votes),
        "ballots": float(len(_ballot_values(votes))),
    }
