"""Voting combiners — many ballots, one decision. Slices 101-105.

- **soft** (101): average the members' probability distributions,
  elect the argmax.
Slices 102-105 add hard, weighted, and confidence-weighted voting
to this module.

All combiners share the contract from :mod:`hugrgate.ensemble.base`:
never raise on ordinary disagreement, always return a valid
:class:`DecisionResult` with the shared ``metadata["ensemble"]``
block, and break ties deterministically.
"""

from __future__ import annotations

from typing import Dict, List

from hugrgate.ensemble.base import (
    MemberVote,
    StrategyContext,
    break_tie,
    finalize_result,
    normalized_entropy,
    require_discrete_spec,
)
from hugrgate.result import DecisionResult

__all__ = [
    "soft_voting",
]


def soft_voting(votes: List[MemberVote],
                ctx: StrategyContext) -> DecisionResult:
    """Average member distributions; elect the argmax.

    ``p(v) = mean_i dist_i(v)`` over usable votes (missing keys count
    as 0, so the average still sums to 1). The winner is the value with
    the highest averaged mass; its probability is that mass and the
    uncertainty is the normalized entropy of the averaged distribution.
    """
    require_discrete_spec(ctx.spec, "soft")
    usable = [v for v in votes if not v.skipped]
    averaged: Dict[str, float] = {}
    for v in usable:
        for key, p in v.distribution.items():
            averaged[key] = averaged.get(key, 0.0) + p
    n = len(usable)
    averaged = {k: p / n for k, p in averaged.items()}
    first_seen: Dict[str, int] = {}
    for i, v in enumerate(usable):
        if v.value is not None and str(v.value) not in first_seen:
            first_seen[str(v.value)] = i
    # Candidates are the averaged keys; every usable vote's value is
    # among them (validate_result guarantees distribution keys cover
    # the value space members claim).
    peak = max(averaged.values())
    tied = [k for k, p in averaged.items() if p == peak]
    winner = break_tie(tied, averaged, first_seen)
    return finalize_result(
        strategy="soft",
        spec=ctx.spec,
        votes=votes,
        weights={v.backend: v.weight for v in usable},
        value=winner,
        probability=averaged[winner],
        distribution=averaged,
        uncertainty=normalized_entropy(averaged),
        winner_share=averaged[winner],
        extra={"averaged_distribution": dict(averaged)},
        model="ensemble:soft",
    )
