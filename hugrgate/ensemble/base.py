"""Ensemble foundations — shared vote plumbing. Slice 101.

Every ensemble strategy in :mod:`hugrgate.ensemble` speaks this one
dialect:

- :class:`MemberVote` — one member backend's ballot, or the recorded
  reason it could not vote (fault isolation: a dead member is skipped
  and named, never fatal).
- :func:`collect_votes` — evaluate every member against the spec with
  per-member fault isolation and contract validation.
- :func:`finalize_result` — build the :class:`DecisionResult` every
  combiner returns, with the shared ``metadata["ensemble"]`` contract:
  strategy name, per-member votes, normalized weights, tally, winner
  share, and the minority report (slice 114 expands it; it is present
  from day one so dissent is never silently dropped).

Determinism: tie-breaks are total and documented
(:func:`break_tie`); no randomness anywhere in this package.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional

from hugrgate.backend import Backend
from hugrgate.errors import (
    Abstention,
    BackendError,
    BackendUnavailable,
    HugrGateError,
    PolicyError,
    SpecError,
)
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec
from hugrgate.validation import validate_result

__all__ = [
    "MemberVote",
    "StrategyContext",
    "Combiner",
    "DISCRETE_SPEC_TYPES",
    "normalize_weights",
    "shannon_entropy",
    "normalized_entropy",
    "break_tie",
    "require_discrete_spec",
    "collect_votes",
    "finalize_result",
]

#: Spec types the voting-family strategies can combine. Numeric specs
#: have no discrete ballots; multilabel ballots are lists (unhashable
#: as single votes) and are left to a future slice.
DISCRETE_SPEC_TYPES = ("categorical", "binary", "ordinal")


@dataclass
class MemberVote:
    """One member's ballot (or its recorded failure to vote)."""

    backend: str
    value: Optional[Any]
    probability: float
    distribution: Dict[str, float] = field(default_factory=dict)
    weight: float = 1.0
    skipped: bool = False
    skip_reason: str = ""
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "value": self.value,
            "probability": self.probability,
            "distribution": dict(self.distribution),
            "weight": self.weight,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "latency_ms": self.latency_ms,
        }


@dataclass
class StrategyContext:
    """What a combiner needs beyond the raw votes."""

    spec: DecisionSpec
    options: Dict[str, Any] = field(default_factory=dict)
    fitted: Any = None  # learned meta-model (stacking/blending/MoE/BMA)


#: A combiner turns member votes into one decision. It must return a
#: fully-formed :class:`DecisionResult` (or an abstention result); it
#: must never raise for ordinary disagreement between members.
Combiner = Callable[[List[MemberVote], StrategyContext], DecisionResult]


def normalize_weights(weights: Mapping[str, float],
                      members: List[str]) -> Dict[str, float]:
    """Validate and normalize member weights to sum to 1.

    Members missing from the map get weight 0: a weights map names the
    members that count. Raises :class:`PolicyError` for unknown
    members, negative or non-finite weights, or a total weight of zero.
    """
    unknown = [k for k in weights if k not in members]
    if unknown:
        raise PolicyError(
            f"weights name unknown member(s): {unknown}; "
            f"members are {members}")
    total = 0.0
    for name in members:
        w = weights.get(name, 0.0)
        if not isinstance(w, (int, float)) or not math.isfinite(w):
            raise PolicyError(
                f"weight for {name!r} must be a finite number, got {w!r}")
        if w < 0:
            raise PolicyError(
                f"weight for {name!r} must be >= 0, got {w}")
        total += w
    if total <= 0:
        raise PolicyError("weights must sum to a positive value")
    return {name: weights.get(name, 0.0) / total for name in members}


def shannon_entropy(distribution: Mapping[str, float]) -> float:
    """Shannon entropy (bits) of a probability distribution."""
    h = 0.0
    for p in distribution.values():
        if p > 0:
            h -= p * math.log2(p)
    return h


def normalized_entropy(distribution: Mapping[str, float]) -> float:
    """Entropy scaled to [0, 1] by the uniform-distribution maximum."""
    n = len(distribution)
    if n <= 1:
        return 0.0
    return shannon_entropy(distribution) / math.log2(n)


def break_tie(candidates: List[str], scores: Mapping[str, float],
              first_seen: Mapping[str, int]) -> str:
    """Deterministic winner among tied candidates.

    Order: highest score, then earliest ballot cast, then
    lexicographic value. Total: the same votes always elect the same
    winner on every machine.
    """
    if not candidates:
        raise HugrGateError("break_tie needs at least one candidate")
    return sorted(
        candidates,
        key=lambda v: (-scores.get(v, 0.0),
                       first_seen.get(v, len(first_seen)),
                       str(v)),
    )[0]


def require_discrete_spec(spec: DecisionSpec, strategy: str) -> None:
    """Voting-family strategies need discrete ballots."""
    if spec.type not in DISCRETE_SPEC_TYPES:
        raise BackendError(
            f"ensemble strategy {strategy!r} needs a discrete spec "
            f"{list(DISCRETE_SPEC_TYPES)}, got {spec.type!r}")


def _skip_vote(backend: str, weight: float, reason: str) -> MemberVote:
    return MemberVote(backend=backend, value=None, probability=0.0,
                      distribution={}, weight=weight, skipped=True,
                      skip_reason=reason)


def collect_votes(members: List[Backend],
                  state: Mapping[str, Any],
                  spec: DecisionSpec,
                  context: Optional[Mapping[str, Any]] = None,
                  weights: Optional[Mapping[str, float]] = None,
                  min_members: int = 1,
                  ensemble_name: str = "ensemble") -> List[MemberVote]:
    """Evaluate every member with per-member fault isolation.

    A member that abstains, fails, violates the result contract, does
    not support the spec, or raises unexpectedly is *skipped* and its
    reason recorded — one sick voter never poisons the election.
    Raises :class:`BackendError` only when fewer than ``min_members``
    usable votes remain.
    """
    if min_members < 1:
        raise PolicyError(
            f"min_members must be >= 1, got {min_members}")
    votes: List[MemberVote] = []
    for member in members:
        if weights is None:
            w = 1.0
        else:
            # A weights map names the members that count; unnamed
            # members get weight 0 (see normalize_weights).
            w = float(weights.get(member.name, 0.0))
        if not member.supports(spec):
            votes.append(_skip_vote(member.name, w, "unsupported_spec"))
            continue
        start = time.perf_counter()
        try:
            result = member.evaluate(state, spec, context)
            validate_result(result, spec)
        except Abstention as e:
            votes.append(_skip_vote(
                member.name, w, f"abstained: {e.message}"))
            continue
        except (BackendError, BackendUnavailable) as e:
            votes.append(_skip_vote(
                member.name, w, f"backend_error: {e.message}"))
            continue
        except SpecError as e:
            votes.append(_skip_vote(
                member.name, w, f"invalid_result: {e.message}"))
            continue
        except Exception as e:  # noqa: BLE001 - isolation is the point
            votes.append(_skip_vote(
                member.name, w,
                f"unexpected_{type(e).__name__}: {e}"))
            continue
        if result.value is None:
            # An abstention-shaped result is an abstention, not a vote
            # for "None" (slice 102 hardening: None is not countable).
            votes.append(_skip_vote(member.name, w, "abstained_result"))
            continue
        latency_ms = (time.perf_counter() - start) * 1000.0
        votes.append(MemberVote(
            backend=member.name,
            value=result.value,
            probability=result.probability,
            distribution=dict(result.distribution),
            weight=w,
            latency_ms=latency_ms,
        ))
    usable = [v for v in votes if not v.skipped]
    if len(usable) < min_members:
        raise BackendError(
            f"ensemble {ensemble_name!r}: only {len(usable)} of "
            f"{len(members)} members produced usable votes "
            f"(need >= {min_members})")
    return votes


def finalize_result(*, strategy: str, spec: DecisionSpec,
                    votes: List[MemberVote],
                    weights: Mapping[str, float],
                    value: Any, probability: float,
                    distribution: Dict[str, float],
                    uncertainty: float,
                    winner_share: Optional[float] = None,
                    extra: Optional[Dict[str, Any]] = None,
                    model: str = "ensemble",
                    latency_ms: float = 0.0,
                    backend: str = "ensemble") -> DecisionResult:
    """Build the combiner's :class:`DecisionResult`.

    Populates the shared ``metadata["ensemble"]`` contract: strategy,
    per-member ballots, normalized weights, the minority report
    (dissenting members are named, never dropped), plus any
    strategy-specific ``extra`` block.
    """
    usable = [v for v in votes if not v.skipped]
    total_w = sum(weights.get(v.backend, 0.0) for v in usable) or 1.0
    norm = {v.backend: weights.get(v.backend, 0.0) / total_w
            for v in usable}
    minority = [
        {"backend": v.backend, "value": v.value,
         "probability": v.probability, "weight": norm[v.backend]}
        for v in usable if v.value != value
    ]
    meta: Dict[str, Any] = {
        "strategy": strategy,
        "members": [v.backend for v in votes],
        "member_votes": [v.to_dict() for v in votes],
        "weights": norm,
        "winner_share": winner_share,
        "minority_report": minority,
        "usable_votes": len(usable),
        "skipped_votes": len(votes) - len(usable),
    }
    if extra:
        meta.update(extra)
    return DecisionResult(
        value=value,
        probability=probability,
        distribution=dict(distribution),
        uncertainty=uncertainty,
        accepted=True,
        backend=backend,
        model=model,
        latency_ms=latency_ms,
        calibration_profile="ensemble",
        metadata={"ensemble": meta},
    )
