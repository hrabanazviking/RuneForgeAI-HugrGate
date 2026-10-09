"""Privacy-constrained objective. Slice 135.

Objectives maximize; privacy *constrains*. :class:`PrivacyConstrainedObjective`
wraps any :class:`~hugrgate.adaptive.cost_quality.RouteObjective` with a
hard admissibility gate derived from the
:class:`~hugrgate.policy.DecisionPolicy` and the candidate's own
properties:

- Under ``privacy_class="strict"``: remote backends are inadmissible,
  and any backend that retains data is inadmissible. This mirrors the
  operator-level :class:`~hugrgate.privacy.PrivacyGuard` — the adaptive
  layer must never learn its way around it.
- The policy's ``backend_allowed`` (allowed-list + remote flag) always
  applies, whatever the privacy class.
- ``candidate.privacy_ok`` is **not trusted**: permission is re-derived
  from ``is_remote`` / ``data_retained`` and the policy. A compromised
  or buggy estimator cannot smuggle a forbidden arm past the gate by
  setting a flag.

Inadmissible arms score ``-inf`` — they can never win a ``max`` — and
:meth:`admissible` filters them out explicitly for callers that prefer
to see the shortlist. When no arm is admissible,
:meth:`require_admissible` raises
:class:`~hugrgate.errors.BackendUnavailable`, the taxonomy's "nothing
can serve this" error.
"""

from __future__ import annotations

from typing import Any, Dict, List

from hugrgate.errors import BackendUnavailable, SpecError
from hugrgate.policy import DecisionPolicy

from hugrgate.adaptive.cost_quality import (
    RouteObjective,
    RoutingCandidate,
)

__all__ = [
    "PrivacyConstrainedObjective",
]


class PrivacyConstrainedObjective(RouteObjective):
    """Hard privacy gate around a soft quality objective."""

    name = "privacy_constrained"

    def __init__(self, objective: RouteObjective,
                 policy: DecisionPolicy) -> None:
        if not isinstance(objective, RouteObjective):
            raise SpecError(
                "PrivacyConstrainedObjective wraps a RouteObjective, got "
                f"{type(objective).__name__}")
        if not isinstance(policy, DecisionPolicy):
            raise SpecError(
                "PrivacyConstrainedObjective needs a DecisionPolicy, got "
                f"{type(policy).__name__}")
        self.objective = objective
        self.policy = policy

    # -- admissibility --------------------------------------------------

    def permitted(self, candidate: RoutingCandidate) -> bool:
        """True iff the policy and privacy class allow this arm.

        Derived from ``is_remote``/``data_retained``/policy — never from
        the advisory ``privacy_ok`` flag.
        """
        if not self.policy.backend_allowed(candidate.name,
                                           candidate.is_remote):
            return False
        if self.policy.privacy_class == "strict":
            if candidate.is_remote:
                return False
            if candidate.data_retained:
                return False
        return True

    def admissible(self,
                   candidates: List[RoutingCandidate]
                   ) -> List[RoutingCandidate]:
        """The subset of candidates the gate permits."""
        return [c for c in candidates if self.permitted(c)]

    def require_admissible(self,
                           candidates: List[RoutingCandidate]
                           ) -> List[RoutingCandidate]:
        admissible = self.admissible(candidates)
        if not admissible:
            raise BackendUnavailable(
                "no routing candidate is admissible under the privacy "
                f"policy (privacy_class={self.policy.privacy_class!r}, "
                f"{len(candidates)} candidates examined)")
        return admissible

    # -- scoring --------------------------------------------------------

    def score(self, candidate: RoutingCandidate) -> float:
        if not self.permitted(candidate):
            return float("-inf")
        return self.objective.score(candidate)

    def best(self, candidates: List[RoutingCandidate]) -> RoutingCandidate:
        """Highest-scoring admissible candidate (raises if none)."""
        admissible = self.require_admissible(candidates)
        return max(admissible, key=self.objective.score)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "objective": self.objective.name,
            "privacy_class": self.policy.privacy_class,
        }
