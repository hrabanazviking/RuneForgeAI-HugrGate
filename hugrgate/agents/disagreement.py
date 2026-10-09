"""Agent Nervous System (Campaign XVI) — agent disagreement handling.

Slice 392.  Fusion (391) always names a winner — but a 51/49
"winner" is a coin flip wearing a crown.  :class:`DisagreementResolver`
decides what *happens* about disagreement:

- ``"fuse"`` — fuse normally; when ``disagreement`` exceeds the
  threshold the resolution is marked ``escalated=True`` (the
  caller moves the ticket up the ladder — the system refuses to
  act on a split vote as if it were consensus);
- ``"majority"`` / ``"highest_confidence"`` — fusion with the
  named method, same escalation-on-split rule;
- ``"human_review"`` — skip deciding entirely: enqueue the vote
  slate to a :class:`HumanReviewQueue` (385) and return a
  resolution with ``escalated=True`` and the review item id.

The threshold is the honesty knob: 0.0 escalates on any dissent,
1.0 never escalates.  Default 0.4 — a clearly-but-not-decisively
split vote goes up, a lone dissenter doesn't.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hugrgate.agents.fusion import (
    AgentVote,
    FusionResult,
    disagreement,
    fuse_confidences,
)
from hugrgate.agents.human_review import HumanReviewQueue, ReviewItem

__all__ = [
    "DISAGREEMENT_STRATEGIES",
    "DisagreementResolver",
    "Resolution",
]

#: Allowed disagreement strategies.
DISAGREEMENT_STRATEGIES: tuple[str, ...] = (
    "fuse", "majority", "highest_confidence", "human_review",
)

_STRATEGY_TO_METHOD = {
    "fuse": "weighted",
    "majority": "majority",
    "highest_confidence": "max_conf",
}


@dataclass(frozen=True)
class Resolution:
    """What happened about the disagreement."""

    label: str
    strategy: str
    confidence: float
    escalated: bool
    reason: str
    votes: tuple[AgentVote, ...] = ()
    fusion: FusionResult | None = None
    review_item_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class DisagreementResolver:
    """Turns vote slates into acted-upon resolutions."""

    def __init__(
        self,
        review_queue: HumanReviewQueue | None = None,
        *,
        disagreement_threshold: float = 0.4,
    ) -> None:
        if not 0.0 <= disagreement_threshold <= 1.0:
            raise ValueError("disagreement_threshold must be in [0, 1]")
        self._review_queue = review_queue
        self._threshold = disagreement_threshold
        self._stats = {"resolved": 0, "escalated": 0,
                       "human_reviewed": 0}

    @property
    def disagreement_threshold(self) -> float:
        """The escalation-on-split threshold."""
        return self._threshold

    def resolve(
        self,
        votes: tuple[AgentVote, ...] | list[AgentVote],
        *,
        strategy: str = "fuse",
        ticket_id: str = "",
        agent_id: str = "",
    ) -> Resolution:
        """Resolve a vote slate per ``strategy``."""
        if strategy not in DISAGREEMENT_STRATEGIES:
            raise ValueError(
                f"strategy must be one of {DISAGREEMENT_STRATEGIES}")
        votes = tuple(votes)
        if strategy == "human_review":
            return self._to_human(votes, ticket_id, agent_id)
        fused = fuse_confidences(votes, method=_STRATEGY_TO_METHOD[strategy])
        split = fused.disagreement > self._threshold
        self._stats["resolved"] += 1
        if split:
            self._stats["escalated"] += 1
        return Resolution(
            label=fused.label,
            strategy=strategy,
            confidence=fused.confidence,
            escalated=split,
            reason=(
                f"disagreement {fused.disagreement:.2f} exceeds "
                f"threshold {self._threshold:.2f}; escalated"
                if split else
                f"disagreement {fused.disagreement:.2f} within "
                f"threshold {self._threshold:.2f}"
            ),
            votes=votes,
            fusion=fused,
        )

    def _to_human(
        self,
        votes: tuple[AgentVote, ...],
        ticket_id: str,
        agent_id: str,
    ) -> Resolution:
        if self._review_queue is None:
            raise ValueError(
                "human_review strategy needs a review queue")
        if not votes:
            raise ValueError("votes must not be empty")
        slate = "; ".join(
            f"{v.agent_id}={v.label}({v.confidence:.2f})" for v in votes
        )
        item = ReviewItem(
            item_id=f"disagree-{ticket_id or 'unticketed'}",
            ticket_id=ticket_id,
            agent_id=agent_id,
            summary=f"agents disagree: {slate[:200]}",
            severity="warning",
            metadata={"disagreement": round(disagreement(votes), 4)},
        )
        item_id = self._review_queue.enqueue(item)
        self._stats["resolved"] += 1
        self._stats["escalated"] += 1
        self._stats["human_reviewed"] += 1
        return Resolution(
            label="",
            strategy="human_review",
            confidence=0.0,
            escalated=True,
            reason=f"vote slate sent to human review as {item_id}",
            votes=votes,
            review_item_id=item_id,
        )

    def stats(self) -> dict[str, int]:
        """Resolver counters (copy)."""
        return dict(self._stats)
