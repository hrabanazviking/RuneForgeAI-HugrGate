"""Voting combiners — many ballots, one decision. Slices 101-105.

- **soft** (101, hardened 103): weight-aware average of the members'
  probability distributions, elect the argmax. A member that votes a
  value with an empty distribution gets it *completed* — its reported
  probability on the voted value, the remainder split uniformly (the
  slice-13 rules-backend semantics) — so an incomplete ballot never
  silently dilutes the average.
- **hard** (102): one ballot per member; majority wins, ties broken
  deterministically (most confident tied camp, then earliest ballot,
  then lexicographic).
- **weighted** (104): hard voting where each ballot counts with its
  member weight; the winner is the argmax of weighted scores and its
  probability is the weighted vote share.
- **confidence** (105): like weighted, but each ballot's weight is
  the member's own reported probability (times its base weight) — a
  confident minority can overrule an unsure majority.

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
    "weighted_voting",
    "confidence_weighted_voting",
]


def _complete_distribution(vote: MemberVote,
                           space: List[str]) -> Dict[str, float]:
    """Complete an empty member distribution.

    The member's reported probability goes on the voted value; the
    remainder is split uniformly across the other options (mirrors the
    rules backend, slice 13). A non-empty distribution is returned
    unchanged — its missing keys are genuine zeros, since a valid
    distribution always sums to 1.
    """
    if vote.distribution:
        return dict(vote.distribution)
    if vote.value is None or vote.value not in space:
        raise BackendError(
            f"soft voting: cannot complete an empty distribution for "
            f"member {vote.backend!r} with value {vote.value!r}")
    others = [o for o in space if o != vote.value]
    if not others:
        return {str(vote.value): 1.0}
    rest = (1.0 - vote.probability) / len(others)
    completed = {o: rest for o in others}
    completed[str(vote.value)] = vote.probability
    return completed


def soft_voting(votes: List[MemberVote],
                ctx: StrategyContext) -> DecisionResult:
    """Weight-aware average of member distributions; elect the argmax.

    ``p(v) = Σᵢ wᵢ·distᵢ(v) / Σᵢ wᵢ`` over usable votes, after
    completing empty member distributions. The winner is the value
    with the highest averaged mass; its probability is that mass and
    the uncertainty is the normalized entropy of the averaged
    distribution.
    """
    require_discrete_spec(ctx.spec, "soft")
    usable = [v for v in votes if not v.skipped]
    if not usable:
        raise BackendError("soft voting: no usable votes")
    space = ctx.spec.value_space()
    total_w = sum(v.weight for v in usable)
    if total_w <= 0:
        raise BackendError(
            "soft voting: total member weight must be positive, "
            f"got {total_w}")
    averaged: Dict[str, float] = {}
    completed: List[str] = []
    for v in usable:
        dist = _complete_distribution(v, space)
        if not v.distribution:
            completed.append(v.backend)
        w = v.weight / total_w
        for key, p in dist.items():
            averaged[key] = averaged.get(key, 0.0) + w * p
    first_seen: Dict[str, int] = {}
    for i, v in enumerate(usable):
        if v.value is not None and str(v.value) not in first_seen:
            first_seen[str(v.value)] = i
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
        extra={"averaged_distribution": dict(averaged),
               "completed_distributions": completed},
        model="ensemble:soft",
    )


def weighted_voting(votes: List[MemberVote],
                    ctx: StrategyContext) -> DecisionResult:
    """Ballots counted with their member weights.

    ``score(v) = Σᵢ wᵢ·[valueᵢ == v]``; the winner is the argmax of
    weighted scores and its probability is the weighted vote share
    (``score(winner) / Σw``). Uncertainty is ``1 - share``. This is
    hard voting where trusted members count more — distinct from soft
    voting, which averages whole distributions.
    """
    require_discrete_spec(ctx.spec, "weighted")
    ballots = _ballots(votes)
    if not ballots:
        raise BackendError("weighted voting: no countable ballots")
    total_w = sum(v.weight for v in ballots)
    if total_w <= 0:
        raise BackendError(
            "weighted voting: total member weight must be positive, "
            f"got {total_w}")
    scores: Dict[str, float] = {}
    first_seen: Dict[str, int] = {}
    for i, v in enumerate(ballots):
        key = str(v.value)
        scores[key] = scores.get(key, 0.0) + v.weight
        if key not in first_seen:
            first_seen[key] = i
    peak = max(scores.values())
    tied = [k for k, s in scores.items() if s == peak]
    winner = break_tie(tied, scores, first_seen)
    share = scores[winner] / total_w
    space = ctx.spec.value_space()
    distribution = {opt: scores.get(opt, 0.0) / total_w for opt in space}
    return finalize_result(
        strategy="weighted",
        spec=ctx.spec,
        votes=votes,
        weights={v.backend: v.weight for v in ballots},
        value=winner,
        probability=share,
        distribution=distribution,
        uncertainty=1.0 - share,
        winner_share=share,
        extra={"weighted_tally": dict(scores)},
        model="ensemble:weighted",
    )


def confidence_weighted_voting(votes: List[MemberVote],
                               ctx: StrategyContext) -> DecisionResult:
    """Ballots weighted by each member's own reported confidence.

    Effective weight ``eᵢ = base_weightᵢ × pᵢ`` where ``pᵢ`` is the
    member's self-reported probability for its voted value; the winner
    is the argmax of ``Σ eᵢ·[valueᵢ == v]`` and its probability is the
    confidence-weighted share. A confident minority can overrule an
    unsure majority — which is exactly the point: members that doubt
    their own vote count less.

    Assumption (documented, tested): member probabilities are at least
    rank-calibrated — higher self-reported confidence must tend to mean
    higher correctness — otherwise this strategy amplifies the most
    overconfident member.
    """
    require_discrete_spec(ctx.spec, "confidence")
    ballots = _ballots(votes)
    if not ballots:
        raise BackendError("confidence voting: no countable ballots")
    effective = [v.weight * v.probability for v in ballots]
    total_e = sum(effective)
    if total_e <= 0:
        raise BackendError(
            "confidence voting: total confidence weight must be "
            f"positive, got {total_e}")
    scores: Dict[str, float] = {}
    first_seen: Dict[str, int] = {}
    for i, v in enumerate(ballots):
        key = str(v.value)
        scores[key] = scores.get(key, 0.0) + effective[i]
        if key not in first_seen:
            first_seen[key] = i
    peak = max(scores.values())
    tied = [k for k, s in scores.items() if s == peak]
    winner = break_tie(tied, scores, first_seen)
    share = scores[winner] / total_e
    space = ctx.spec.value_space()
    distribution = {opt: scores.get(opt, 0.0) / total_e for opt in space}
    return finalize_result(
        strategy="confidence",
        spec=ctx.spec,
        votes=votes,
        weights={v.backend: v.weight for v in ballots},
        value=winner,
        probability=share,
        distribution=distribution,
        uncertainty=1.0 - share,
        winner_share=share,
        extra={"confidence_scores": dict(scores),
               "effective_weights": {v.backend: effective[i]
                                     for i, v in enumerate(ballots)}},
        model="ensemble:confidence",
    )


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
