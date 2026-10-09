"""Disagreement detection — verdicts from diversity. Slice 111.

:class:`DisagreementDetector` turns the raw diversity metrics (slice
110) into a verdict — none / mild / strong — with the dissenting
members named. Slices 112 (escalation) and 114 (minority-report
preservation) build on the :class:`DisagreementReport` defined here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hugrgate.ensemble.base import MemberVote
from hugrgate.ensemble.diversity import (
    disagreement_rate,
    vote_entropy,
    winner_margin,
)
from hugrgate.errors import PolicyError

__all__ = [
    "LEVEL_NONE",
    "LEVEL_MILD",
    "LEVEL_STRONG",
    "DisagreementThresholds",
    "DisagreementReport",
    "DisagreementDetector",
]

LEVEL_NONE = "none"
LEVEL_MILD = "mild"
LEVEL_STRONG = "strong"
LEVELS = (LEVEL_NONE, LEVEL_MILD, LEVEL_STRONG)


@dataclass
class DisagreementThresholds:
    """Tunable detection thresholds (all in natural metric units)."""

    strong_disagreement: float = 0.5
    mild_disagreement: float = 0.2
    strong_entropy: float = 1.0
    mild_entropy: float = 0.5
    mild_margin: float = 0.3

    def __post_init__(self):
        for name in ("strong_disagreement", "mild_disagreement"):
            v = getattr(self, name)
            if not 0.0 <= v <= 1.0:
                raise PolicyError(f"{name} must be in [0,1], got {v}")
        for name in ("strong_entropy", "mild_entropy", "mild_margin"):
            v = getattr(self, name)
            if v < 0:
                raise PolicyError(f"{name} must be >= 0, got {v}")
        if self.strong_disagreement < self.mild_disagreement:
            raise PolicyError(
                "strong_disagreement must be >= mild_disagreement")
        if self.strong_entropy < self.mild_entropy:
            raise PolicyError(
                "strong_entropy must be >= mild_entropy")


@dataclass
class DisagreementReport:
    """The detector's verdict on one round of ballots."""

    level: str
    disagree: bool
    vote_entropy: float
    disagreement_rate: float
    winner_margin: float
    plurality_value: Optional[str]
    dissenters: List[str] = field(default_factory=list)
    ballots: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "disagree": self.disagree,
            "vote_entropy": self.vote_entropy,
            "disagreement_rate": self.disagreement_rate,
            "winner_margin": self.winner_margin,
            "plurality_value": self.plurality_value,
            "dissenters": list(self.dissenters),
            "ballots": self.ballots,
        }


class DisagreementDetector:
    """Classify member disagreement as none / mild / strong."""

    def __init__(self,
                 thresholds: Optional[DisagreementThresholds] = None):
        self.thresholds = thresholds or DisagreementThresholds()

    def detect(self, votes: List[MemberVote]) -> DisagreementReport:
        ballots = [(v.backend, str(v.value)) for v in votes
                   if not v.skipped and v.value is not None]
        if len(ballots) < 2:
            # One voter cannot disagree with itself.
            return DisagreementReport(
                level=LEVEL_NONE, disagree=False,
                vote_entropy=0.0, disagreement_rate=0.0,
                winner_margin=1.0 if ballots else 0.0,
                plurality_value=ballots[0][1] if ballots else None,
                dissenters=[], ballots=len(ballots))
        t = self.thresholds
        entropy = vote_entropy(votes)
        rate = disagreement_rate(votes)
        margin = winner_margin(votes)
        counts: Dict[str, int] = {}
        first_seen: Dict[str, int] = {}
        for i, (_, value) in enumerate(ballots):
            counts[value] = counts.get(value, 0) + 1
            if value not in first_seen:
                first_seen[value] = i
        peak = max(counts.values())
        plurality = sorted(
            [v for v, c in counts.items() if c == peak],
            key=lambda v: first_seen[v])[0]
        dissenters = [b for b, v in ballots if v != plurality]
        if (rate >= t.strong_disagreement or entropy >= t.strong_entropy):
            level = LEVEL_STRONG
        elif (rate >= t.mild_disagreement or entropy >= t.mild_entropy
              or margin < t.mild_margin):
            level = LEVEL_MILD
        else:
            level = LEVEL_NONE
        return DisagreementReport(
            level=level, disagree=level != LEVEL_NONE,
            vote_entropy=entropy, disagreement_rate=rate,
            winner_margin=margin, plurality_value=plurality,
            dissenters=dissenters, ballots=len(ballots))
