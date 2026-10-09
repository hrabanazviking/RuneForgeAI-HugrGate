"""Disagreement detection and escalation. Slices 111-112.

:class:`DisagreementDetector` (111) turns the raw diversity metrics
(slice 110) into a verdict — none / mild / strong — with the
dissenting members named. :class:`EscalationPolicy` + :func:`escalate`
(112) map that verdict to an action: decide anyway, flag for review,
abstain with a named reason, or fall back to a designated backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from hugrgate.abstain import abstain, mark_for_review
from hugrgate.backend import Backend
from hugrgate.ensemble.base import MemberVote
from hugrgate.ensemble.diversity import (
    disagreement_rate,
    vote_entropy,
    winner_margin,
)
from hugrgate.errors import BackendError, PolicyError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "LEVEL_NONE",
    "LEVEL_MILD",
    "LEVEL_STRONG",
    "DisagreementThresholds",
    "DisagreementReport",
    "DisagreementDetector",
    "EscalationPolicy",
    "escalate",
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


@dataclass
class EscalationPolicy:
    """What to do when members disagree.

    Actions: ``"none"`` (decide anyway), ``"review"`` (flag the result
    for a human), ``"abstain"`` (refuse with a named reason),
    ``"fallback"`` (use the fallback backend's result instead).
    """

    mild_action: str = "none"
    strong_action: str = "review"
    fallback_backend: Optional[Backend] = None

    ACTIONS = ("none", "review", "abstain", "fallback")

    def __post_init__(self):
        for name in ("mild_action", "strong_action"):
            action = getattr(self, name)
            if action not in self.ACTIONS:
                raise PolicyError(
                    f"{name} must be one of {list(self.ACTIONS)}, "
                    f"got {action!r}")
        if self.strong_action == "fallback" and \
                self.fallback_backend is None:
            raise PolicyError(
                "strong_action='fallback' needs a fallback_backend")
        if self.mild_action == "fallback" and \
                self.fallback_backend is None:
            raise PolicyError(
                "mild_action='fallback' needs a fallback_backend")


def escalate(result: DecisionResult, spec: DecisionSpec,
             report: DisagreementReport,
             policy: EscalationPolicy,
             state: Optional[Mapping[str, Any]] = None,
             context: Optional[Mapping[str, Any]] = None
             ) -> DecisionResult:
    """Apply the escalation policy to a disagreed-upon result.

    Never raises for the disagreement itself: ``review`` flags,
    ``abstain`` refuses with a named reason, ``fallback`` asks the
    fallback backend (its failure *does* raise, honestly).
    """
    action = (policy.mild_action if report.level == LEVEL_MILD
              else policy.strong_action if report.level == LEVEL_STRONG
              else "none")
    reason = (f"member disagreement ({report.level}): "
              f"{report.disagreement_rate:.2f} of ballot pairs differ, "
              f"dissenters={report.dissenters or 'none'}")
    if action == "none":
        result.metadata.setdefault("ensemble", {})[
            "disagreement"] = report.to_dict()
        return result
    if action == "review":
        flagged = mark_for_review(result, reason)
        flagged.metadata.setdefault("ensemble", {})[
            "disagreement"] = report.to_dict()
        return flagged
    if action == "abstain":
        out = abstain(spec, reason=reason, backend=result.backend,
                      metadata={"disagreement": report.to_dict(),
                                "fallback_used": result.fallback_used})
        out.metadata.setdefault("ensemble", {})[
            "disagreement"] = report.to_dict()
        return out
    # action == "fallback"
    assert policy.fallback_backend is not None  # validated at init
    try:
        fb_result = policy.fallback_backend.evaluate(
            state or {}, spec, context)
    except Exception as e:
        raise BackendError(
            f"disagreement fallback backend "
            f"{policy.fallback_backend.name!r} failed: {e}")
    fb_result.fallback_used = True
    fb_result.metadata["disagreement_fallback"] = reason
    fb_result.metadata.setdefault("ensemble", {})[
        "disagreement"] = report.to_dict()
    return fb_result


@dataclass
class MinorityReport:
    """A dissenting member's preserved opinion (slice 114)."""

    backend: str
    value: Any
    probability: float
    weight: float

    def to_text(self) -> str:
        return (f"{self.backend} dissented: voted {self.value!r} "
                f"at p={self.probability:.3f} "
                f"(weight {self.weight:.3f})")


def minority_report(result: DecisionResult) -> List[MinorityReport]:
    """Extract the preserved minority opinions from a result.

    Always returns a list (possibly empty) — the key is present on
    every ensemble result since slice 101, so dissent can never be
    silently dropped.
    """
    meta = result.metadata.get("ensemble", {})
    return [MinorityReport(backend=r.get("backend", "?"),
                           value=r.get("value"),
                           probability=float(r.get("probability", 0.0)),
                           weight=float(r.get("weight", 0.0)))
            for r in meta.get("minority_report", [])]
