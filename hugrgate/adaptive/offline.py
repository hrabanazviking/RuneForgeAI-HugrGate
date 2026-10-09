"""Offline policy learning. Slice 131.

Online bandit updates (slice 130) learn from the live stream, but the
telemetry log (slice 126) is also a training set. :class:`OfflinePolicyLearning`
fits a fresh :class:`~hugrgate.adaptive.bandit.ContextualBanditAdapter`
from logged events *without* touching production:

- Only **labeled, non-shadow** events are used. Unlabeled events carry
  no reward signal; shadow records (slice 143) were never served, so
  training on them would learn a policy for traffic that never existed.
- Rewards come from the attached outcome's ``quality`` (falling back to
  ``immediate_quality``); the logging policy's propensities correct for
  selection bias via **inverse-propensity weighting**, clipped to
  ``[propensity_clip]`` so one lucky rare event can't dominate.
- :meth:`diagnostics` reports the effective sample size and how many
  events were skipped and why — an offline fit that silently trains on
  twelve events is worse than no fit at all.

This is the batch complement to the online adapter: retrain nightly (or
on drift alerts, slice 148), validate counterfactually (slice 144),
then promote through versioning (slice 146) and shadow mode (slice 143)
before serving.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from hugrgate.errors import SpecError

from hugrgate.adaptive.bandit import ContextualBanditAdapter
from hugrgate.adaptive.telemetry import RouteEvent

__all__ = [
    "LearningDiagnostics",
    "OfflinePolicyLearning",
]


@dataclass
class LearningDiagnostics:
    """What the offline fit saw and what it skipped."""

    n_events: int = 0
    n_used: int = 0
    n_unlabeled: int = 0
    n_shadow: int = 0
    n_bad_propensity: int = 0
    n_clipped: int = 0
    effective_sample_size: float = 0.0
    arms: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.arms is None:
            self.arms = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_events": self.n_events,
            "n_used": self.n_used,
            "n_unlabeled": self.n_unlabeled,
            "n_shadow": self.n_shadow,
            "n_bad_propensity": self.n_bad_propensity,
            "n_clipped": self.n_clipped,
            "effective_sample_size": self.effective_sample_size,
            "arms": list(self.arms),
        }


class OfflinePolicyLearning:
    """Batch-fit a bandit policy from logged routing telemetry."""

    def __init__(self, feature_names: Sequence[str], *,
                 alpha: float = 1.0, ridge: float = 1.0,
                 min_propensity: float = 1e-3,
                 max_weight: float = 100.0,
                 min_events: int = 1) -> None:
        if not 0.0 < min_propensity <= 1.0:
            raise SpecError(
                f"min_propensity must be in (0,1], got {min_propensity}")
        if max_weight <= 0:
            raise SpecError(f"max_weight must be positive, got {max_weight}")
        if min_events < 1:
            raise SpecError(f"min_events must be >= 1, got {min_events}")
        self.feature_names = list(feature_names)
        self.alpha = alpha
        self.ridge = ridge
        self.min_propensity = min_propensity
        self.max_weight = max_weight
        self.min_events = min_events
        self._diagnostics = LearningDiagnostics()

    @property
    def diagnostics(self) -> LearningDiagnostics:
        return self._diagnostics

    def _reward(self, event: RouteEvent) -> Optional[float]:
        if event.outcome is not None and "quality" in event.outcome:
            return float(event.outcome["quality"])
        if event.immediate_quality:
            return float(event.immediate_quality)
        return None

    def fit(self, events: Iterable[RouteEvent]) -> ContextualBanditAdapter:
        """Fit a bandit from labeled, non-shadow telemetry events."""
        adapter = ContextualBanditAdapter(
            self.feature_names, alpha=self.alpha, ridge=self.ridge)
        diag = LearningDiagnostics()
        weights: List[float] = []
        for event in events:
            diag.n_events += 1
            if event.shadow:
                diag.n_shadow += 1
                continue
            reward = self._reward(event)
            if reward is None:
                diag.n_unlabeled += 1
                continue
            propensity = event.propensities.get(event.chosen, 0.0)
            if propensity < self.min_propensity:
                diag.n_bad_propensity += 1
                continue
            weight = 1.0 / propensity
            if weight > self.max_weight:
                weight = self.max_weight
                diag.n_clipped += 1
            adapter.update(event.chosen, event.features, reward,
                           weight=weight)
            weights.append(weight)
            diag.n_used += 1
        if diag.n_used < self.min_events:
            raise SpecError(
                f"offline learning needs at least {self.min_events} usable "
                f"events, got {diag.n_used} (unlabeled={diag.n_unlabeled}, "
                f"shadow={diag.n_shadow}, bad_propensity="
                f"{diag.n_bad_propensity})")
        if weights:
            total = sum(weights)
            diag.effective_sample_size = (total * total) / sum(
                w * w for w in weights)
        diag.arms = adapter.arms()
        self._diagnostics = diag
        return adapter

    def fit_store(self, store: Any) -> ContextualBanditAdapter:
        """Convenience: fit from every event in a
        :class:`~hugrgate.adaptive.telemetry.TelemetryStore`."""
        return self.fit(store.events())
