"""Outcome-conditioned retrieval. Slice 311.

Plain recall answers "what happened in similar situations?".
Conditioned recall answers the sharper questions:

- "what happened in similar situations *that worked*?" —
  ``outcome_kinds={"success"}``;
- "what went wrong before?" — ``outcome_kinds={"failure"}``;
- "show me only verified precedents" —
  ``require_truth_agreement=True`` keeps episodes whose ground truth
  agrees with the attached outcome (via
  :func:`~hugrgate.memory.groundtruth.outcome_agrees`).

Episodes with no outcome attached are excluded unless
``include_unknown=True`` — conditioning on an outcome you do not have
is how survivorship bias sneaks in, so the default is strict.
"""

from __future__ import annotations

from hugrgate.memory.groundtruth import outcome_agrees
from hugrgate.memory.outcomes import OUTCOME_KINDS
from hugrgate.memory.query import MemoryQuery
from hugrgate.memory.retrieval import RetrievalResult, retrieve
from hugrgate.memory.types import EpisodeLike, HistoryLike

__all__ = [
    "retrieve_conditioned",
]


def retrieve_conditioned(
    history: HistoryLike,
    query_features: dict[str, float], *,
    outcome_kinds: set[str] | frozenset[str] | None = frozenset({"success"}),
    include_unknown: bool = False,
    require_truth_agreement: bool = False,
    **retrieve_kwargs,
) -> list[RetrievalResult]:
    """Recall precedents filtered by observed outcome kind.

    ``outcome_kinds=None`` disables kind filtering (still honors
    ``include_unknown`` / ``require_truth_agreement``).
    Remaining scoring is :func:`~hugrgate.memory.retrieval.retrieve`
    with ``episodes=`` bound to the conditioned subset.
    """
    if outcome_kinds is not None:
        unknown = set(outcome_kinds) - set(OUTCOME_KINDS)
        if unknown:
            raise ValueError(
                f"unknown outcome kind(s): {sorted(unknown)}; expected "
                f"a subset of {OUTCOME_KINDS} or None")

    episodes: list[EpisodeLike] = history.find(MemoryQuery())
    conditioned: list[EpisodeLike] = []
    for episode in episodes:
        outcome = episode.outcome
        if outcome is None:
            if include_unknown and not require_truth_agreement:
                conditioned.append(episode)
            continue
        if outcome_kinds is not None and outcome.kind not in outcome_kinds:
            continue
        if require_truth_agreement:
            truth = episode.ground_truth
            if truth is None or outcome_agrees(truth, outcome) is not True:
                continue
        conditioned.append(episode)
    return retrieve(history, query_features, episodes=conditioned,
                    **retrieve_kwargs)
