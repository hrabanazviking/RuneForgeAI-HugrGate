"""Adaptive-route explanations. Slice 147.

A router that cannot say *why* it chose an arm is a liability in
review, incident response, and regulated settings.
:class:`AdaptiveRouteExplainer` turns a routing decision's internals —
per-arm scores, feature contributions, competence profiles, objective
weights — into a structured :class:`RouteExplanation` with both
machine-readable fields and a human-readable narrative.

Explanation sources, in order of specificity:

1. **Feature contributions** — when the caller supplies per-feature
   weights (e.g. the bandit's learned ``theta`` for the chosen arm),
   ``contribution = weight × feature_value`` ranks what the context
   actually pushed on.
2. **Score margins** — how far ahead the winner was, and who the
   runner-up was.
3. **Competence context** — the winner's Wilson lower bound vs the
   field, when profiles are supplied.
4. **Objective weights** — the value judgments behind the scores, when
   a multi-objective router is supplied.

The explainer never invents causes: every sentence in ``text`` cites a
number present in the explanation. Unknowns are stated as unknowns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from hugrgate.errors import SpecError

from hugrgate.adaptive.cost_quality import RoutingCandidate
from hugrgate.adaptive.competence import BackendCompetenceProfiles

__all__ = [
    "FeatureContribution",
    "RouteExplanation",
    "AdaptiveRouteExplainer",
]


@dataclass(frozen=True)
class FeatureContribution:
    """One feature's push on the decision."""

    feature: str
    value: float
    weight: float
    contribution: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature": self.feature,
            "value": self.value,
            "weight": self.weight,
            "contribution": self.contribution,
        }


@dataclass(frozen=True)
class RouteExplanation:
    """Why this arm won, in data and in words."""

    chosen: str
    scores: Dict[str, float]
    runner_up: Optional[str]
    margin: float
    top_features: List[FeatureContribution] = field(default_factory=list)
    competence_note: Optional[str] = None
    objective_note: Optional[str] = None
    text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chosen": self.chosen,
            "scores": dict(self.scores),
            "runner_up": self.runner_up,
            "margin": self.margin,
            "top_features": [f.to_dict() for f in self.top_features],
            "competence_note": self.competence_note,
            "objective_note": self.objective_note,
            "text": self.text,
        }


class AdaptiveRouteExplainer:
    """Build :class:`RouteExplanation` from decision internals."""

    def __init__(self, *,
                 profiles: Optional[BackendCompetenceProfiles] = None,
                 top_k_features: int = 3) -> None:
        if top_k_features < 1:
            raise SpecError(
                f"top_k_features must be >= 1, got {top_k_features}")
        self.profiles = profiles
        self.top_k_features = top_k_features

    def explain(self, chosen: str,
                scores: Mapping[str, float],
                features: Optional[Mapping[str, float]] = None,
                feature_weights: Optional[Mapping[str, float]] = None,
                objective_note: Optional[str] = None) -> RouteExplanation:
        """Explain why ``chosen`` won given per-arm ``scores``."""
        score_map = dict(scores)
        if chosen not in score_map:
            raise SpecError(
                f"chosen arm {chosen!r} has no score; scored arms: "
                f"{sorted(score_map)}")
        ordered = sorted(score_map.items(), key=lambda kv: (-kv[1], kv[0]))
        runner_up = ordered[1][0] if len(ordered) > 1 else None
        margin = (ordered[0][1] - ordered[1][1]) if len(ordered) > 1 else 0.0

        contributions: List[FeatureContribution] = []
        if features is not None and feature_weights is not None:
            for name, value in features.items():
                weight = feature_weights.get(name, 0.0)
                contributions.append(FeatureContribution(
                    feature=name, value=float(value),
                    weight=float(weight),
                    contribution=float(weight) * float(value)))
            contributions.sort(key=lambda c: (-abs(c.contribution), c.feature))
            contributions = contributions[:self.top_k_features]

        competence_note = self._competence_note(chosen, score_map)

        lines = [
            f"Chose {chosen!r} with score {score_map[chosen]:.4f} "
            f"over {len(score_map) - 1} alternative(s)."
        ]
        if runner_up is not None:
            lines.append(
                f"Runner-up was {runner_up!r} "
                f"(score {score_map[runner_up]:.4f}); "
                f"margin {margin:.4f}.")
        else:
            lines.append("It was the only candidate.")
        for contrib in contributions:
            direction = "for" if contrib.contribution >= 0 else "against"
            lines.append(
                f"Feature {contrib.feature!r}={contrib.value:.4f} pushed "
                f"{direction} the choice "
                f"(weight {contrib.weight:.4f}, contribution "
                f"{contrib.contribution:+.4f}).")
        if competence_note:
            lines.append(competence_note)
        if objective_note:
            lines.append(objective_note)
        return RouteExplanation(
            chosen=chosen,
            scores=score_map,
            runner_up=runner_up,
            margin=margin,
            top_features=contributions,
            competence_note=competence_note,
            objective_note=objective_note,
            text=" ".join(lines),
        )

    def _competence_note(self, chosen: str,
                         scores: Mapping[str, float]) -> Optional[str]:
        if self.profiles is None:
            return None
        profile = self.profiles.get(chosen)
        if profile is None or profile.attempts == 0:
            return (f"No competence history for {chosen!r}; the choice "
                    f"rests on priors and context, not track record.")
        ranked = self.profiles.ranked()
        position = next((i for i, p in enumerate(ranked)
                         if p.backend == chosen), None)
        field_size = len(ranked)
        return (f"{chosen!r} has {profile.attempts} recorded attempts "
                f"(success rate {profile.success_rate:.2f}, Wilson lower "
                f"bound {profile.wilson_lower:.3f}), ranked "
                f"#{position + 1 if position is not None else '?'} of "
                f"{field_size} backends by conservative competence.")

    def explain_candidates(
            self, candidates: Sequence[RoutingCandidate],
            score_fn: Any) -> RouteExplanation:
        """Convenience: score candidates with ``score_fn`` and explain."""
        scores = {c.name: float(score_fn(c)) for c in candidates}
        if not scores:
            raise SpecError("cannot explain an empty candidate list")
        best_score = max(scores.values())
        # Deterministic tie-break: smallest arm name wins.
        chosen = min(n for n, s in scores.items() if s == best_score)
        return self.explain(chosen, scores)
