"""Backend reliability weighting — trust, but verify. Slice 116.

Static weights encode operator *belief*; reliability weights encode
*evidence*. :class:`ReliabilityTracker` records each member's labeled
outcomes and converts the track record into weights:

- ``reliability(m)`` — Laplace-smoothed accuracy
  ``(successes + s) / (total + 2s)`` (default ``s=1``): a new member
  starts at 0.5, not 0 — no one is condemned without evidence;
- :meth:`ReliabilityTracker.weights` — reliabilities (times any
  penalties) normalized to sum to 1, ready to feed
  ``Ensemble(weights=...)``;
- :meth:`ReliabilityTracker.apply_correlation_report` — the slice-115
  wiring: inside each correlated-error clique, all but the most
  reliable member are penalized by ``factor`` (default 0.5), so
  duplicated minds stop buying duplicate influence.

Usage::

    tracker = ReliabilityTracker(["a", "b", "c"])
    tracker.observe("a", correct=True)   # ... from labeled feedback
    ens = Ensemble(members, strategy="weighted",
                   weights=tracker.weights())
"""

from __future__ import annotations

from typing import Dict, List

from hugrgate.ensemble.correlation import CorrelatedErrorReport
from hugrgate.errors import PolicyError

__all__ = [
    "ReliabilityTracker",
]


class ReliabilityTracker:
    """Track per-member accuracy and convert it to ensemble weights."""

    def __init__(self, members: List[str], smoothing: float = 1.0):
        if not members:
            raise PolicyError(
                "ReliabilityTracker needs at least one member")
        if len(set(members)) != len(members):
            raise PolicyError(
                f"member names must be unique, got {members}")
        if not smoothing > 0:
            raise PolicyError(
                f"smoothing must be > 0, got {smoothing}")
        self.members = list(members)
        self.smoothing = float(smoothing)
        self._successes: Dict[str, int] = {m: 0 for m in members}
        self._totals: Dict[str, int] = {m: 0 for m in members}
        self._penalties: Dict[str, float] = {m: 1.0 for m in members}

    def _check(self, member: str) -> None:
        if member not in self._totals:
            raise PolicyError(
                f"unknown member {member!r}; members are {self.members}")

    def observe(self, member: str, correct: bool) -> None:
        """Record one labeled outcome for ``member``."""
        self._check(member)
        self._totals[member] += 1
        if correct:
            self._successes[member] += 1

    def observe_many(self, member: str, correct: List[bool]) -> None:
        for c in correct:
            self.observe(member, c)

    def reliability(self, member: str) -> float:
        """Laplace-smoothed accuracy in (0, 1)."""
        self._check(member)
        s = self.smoothing
        return ((self._successes[member] + s)
                / (self._totals[member] + 2 * s))

    def raw_accuracy(self, member: str) -> float:
        """Unsmoothed accuracy; 0.5 when unobserved (no evidence)."""
        self._check(member)
        total = self._totals[member]
        if total == 0:
            return 0.5
        return self._successes[member] / total

    def penalize(self, member: str, factor: float) -> None:
        """Scale ``member``'s weight by ``factor`` in [0, 1]."""
        self._check(member)
        if not 0.0 <= factor <= 1.0:
            raise PolicyError(
                f"penalty factor must be in [0,1], got {factor}")
        self._penalties[member] = float(factor)

    def clear_penalties(self) -> None:
        for m in self.members:
            self._penalties[m] = 1.0

    def apply_correlation_report(self, report: CorrelatedErrorReport,
                                 factor: float = 0.5) -> None:
        """Penalize duplicated minds (slice-115 wiring).

        In each correlated-error clique, the most reliable member
        keeps full weight; the rest are penalized by ``factor``.
        """
        if not 0.0 <= factor <= 1.0:
            raise PolicyError(
                f"penalty factor must be in [0,1], got {factor}")
        for clique in report.cliques:
            ranked = sorted(clique,
                            key=lambda m: (-self.reliability(m), m))
            for member in ranked[1:]:
                self.penalize(member, factor)

    def weights(self) -> Dict[str, float]:
        """Normalized reliability × penalty weights (sum to 1)."""
        raw = {m: self.reliability(m) * self._penalties[m]
               for m in self.members}
        total = sum(raw.values())
        if total <= 0:
            raise PolicyError(
                "reliability weights sum to zero; "
                "clear penalties or add observations")
        return {m: v / total for m, v in raw.items()}

    def observation_counts(self) -> Dict[str, int]:
        return dict(self._totals)

    def to_dict(self) -> Dict[str, object]:
        return {
            "members": list(self.members),
            "smoothing": self.smoothing,
            "reliabilities": {m: self.reliability(m)
                              for m in self.members},
            "observations": dict(self._totals),
            "penalties": dict(self._penalties),
            "weights": self.weights(),
        }
