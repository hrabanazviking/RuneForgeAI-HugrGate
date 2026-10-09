"""Agent Nervous System (Campaign XVI) — agent confidence fusion.

Slice 391.  Dispatch (386) fans out; several agents answer; now
*one* answer must win.  :func:`fuse_confidences` reconciles
weighted agent votes into a single label + confidence:

- ``"weighted"`` — each label's mass is ``Σ weight·confidence``;
  the winner is the heaviest label and its fused confidence is
  the weight-normalized mean confidence of its supporters;
- ``"majority"`` — most votes wins (one agent, one vote);
  ties break toward the higher total confidence, then the
  lexicographically smallest label — deterministic, always;
- ``"max_conf"`` — the single most confident vote wins outright
  (for when one specialist should overrule the crowd).

:func:`disagreement` scores 0..1 how split the vote was —
``1 - winner_mass/total_mass`` — so the disagreement handler
(392) knows when fusion was a coin flip wearing a winner's
mask.  Zero-mass votes (all weights 0) are a ``ValueError``:
fusion with no evidence is not fusion.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "FUSION_METHODS",
    "AgentVote",
    "FusionResult",
    "disagreement",
    "fuse_confidences",
]

#: Allowed fusion methods.
FUSION_METHODS: tuple[str, ...] = ("weighted", "majority", "max_conf")


@dataclass(frozen=True)
class AgentVote:
    """One agent's vote."""

    agent_id: str
    label: str
    confidence: float
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ValueError("agent_id must be non-empty")
        if not self.label:
            raise ValueError("label must be non-empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if self.weight < 0:
            raise ValueError("weight must be >= 0")


@dataclass(frozen=True)
class FusionResult:
    """The reconciled answer."""

    label: str
    confidence: float
    method: str
    votes: tuple[AgentVote, ...]
    disagreement: float


def _validate(votes: tuple[AgentVote, ...] | list[AgentVote],
              method: str) -> tuple[AgentVote, ...]:
    if method not in FUSION_METHODS:
        raise ValueError(f"method must be one of {FUSION_METHODS}")
    votes = tuple(votes)
    if not votes:
        raise ValueError("votes must not be empty")
    if sum(v.weight for v in votes) <= 0:
        raise ValueError("total vote weight must be > 0")
    return votes


def disagreement(votes: tuple[AgentVote, ...] | list[AgentVote]) -> float:
    """How split the vote is, 0 (unanimous) to <1 (even split)."""
    votes = tuple(votes)
    if not votes:
        raise ValueError("votes must not be empty")
    mass: dict[str, float] = {}
    for v in votes:
        mass[v.label] = mass.get(v.label, 0.0) + v.weight * v.confidence
    total = sum(mass.values())
    if total <= 0:
        return 1.0
    return 1.0 - max(mass.values()) / total


def fuse_confidences(
    votes: tuple[AgentVote, ...] | list[AgentVote],
    method: str = "weighted",
) -> FusionResult:
    """Fuse ``votes`` into one label + confidence."""
    votes = _validate(votes, method)
    if method == "weighted":
        mass: dict[str, float] = {}
        wsum: dict[str, float] = {}
        for v in votes:
            mass[v.label] = mass.get(v.label, 0.0) + v.weight * v.confidence
            wsum[v.label] = wsum.get(v.label, 0.0) + v.weight
        label = min(mass, key=lambda lab: (-mass[lab], lab))
        confidence = mass[label] / wsum[label]
    elif method == "majority":
        counts: dict[str, int] = {}
        confsum: dict[str, float] = {}
        for v in votes:
            counts[v.label] = counts.get(v.label, 0) + 1
            confsum[v.label] = confsum.get(v.label, 0.0) + v.confidence
        label = min(
            counts, key=lambda lab: (-counts[lab], -confsum[lab], lab))
        confidence = confsum[label] / counts[label]
    else:  # max_conf
        best = min(votes, key=lambda v: (-v.confidence, v.agent_id))
        label = best.label
        confidence = best.confidence
    return FusionResult(
        label=label,
        confidence=round(min(1.0, max(0.0, confidence)), 4),
        method=method,
        votes=votes,
        disagreement=round(disagreement(votes), 4),
    )
