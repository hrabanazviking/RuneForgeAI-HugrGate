"""Voting combiners — many ballots, one decision. Slices 101-105.

- **soft** (101): average the members' probability distributions,
  elect the argmax.
- **hard** (102): one ballot per member; majority wins, ties broken
  deterministically (most confident tied camp, then earliest ballot,
  then lexicographic).

Slices 104-105 add weighted and confidence-weighted voting here.

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
from hugrgate.errors import BackendError
from hugrgate.result import DecisionResult

__all__ = [
    "soft_voting",
    "hard_voting",
]


def _ballots(votes: List[MemberVote]) -> List[MemberVote]:
    """Usable votes with an actual value to count."""
    return [v for v in votes if not v.skipped and v.value is not None]


def hard_voting(votes: List[MemberVote],
                ctx: StrategyContext) -> DecisionResult:
    """One member, one ballot; the majority value wins.

    ``P(winner)`` is the winner's vote share (ballots for the winner /
    ballots cast); uncertainty is ``1 - share``. Ties break by the
    tied camp's total self-reported confidence, then earliest ballot,
    then lexicographic value — fully deterministic.
    """
    require_discrete_spec(ctx.spec, "hard")
    ballots = _ballots(votes)
    if not ballots:
        raise BackendError("hard voting: no countable ballots")
    tally: Dict[str, int] = {}
    confidence: Dict[str, float] = {}
    first_seen: Dict[str, int] = {}
    for i, v in enumerate(ballots):
        key = str(v.value)
        tally[key] = tally.get(key, 0) + 1
        confidence[key] = confidence.get(key, 0.0) + v.probability
        if key not in first_seen:
            first_seen[key] = i
    peak = max(tally.values())
    tied = [k for k, c in tally.items() if c == peak]
    tie_broken_by = "order"
    if len(tied) > 1:
        # Most self-confident tied camp first; break_tie keeps the
        # documented total order for anything still tied.
        best_conf = max(confidence[k] for k in tied)
        confident = [k for k in tied if confidence[k] == best_conf]
        if len(confident) < len(tied):
            tie_broken_by = "confidence"
        tied = confident
    winner = break_tie(tied, {k: float(tally[k]) for k in tied},
                       first_seen)
    share = tally[winner] / len(ballots)
    space = ctx.spec.value_space()
    distribution = {opt: tally.get(opt, 0) / len(ballots) for opt in space}
    return finalize_result(
        strategy="hard",
        spec=ctx.spec,
        votes=votes,
        weights={v.backend: v.weight for v in ballots},
        value=winner,
        probability=share,
        distribution=distribution,
        uncertainty=1.0 - share,
        winner_share=share,
        extra={"tally": dict(tally), "tie_broken_by": tie_broken_by},
        model="ensemble:hard",
    )


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
