"""Adaptive-route drift detection. Slice 148.

Learning never stops, and neither does the world changing underneath
it. :class:`AdaptiveRouteDriftDetector` watches two signals for
distribution shift against a reference window:

- **route drift** — the share of traffic each arm receives (a policy
  that suddenly routes 90% to one backend is telling you something);
- **reward drift** — the distribution of observed outcome quality
  (the world getting harder, or easier, for everyone).

Both use the Population Stability Index from :mod:`hugrgate.drift`
(``PSI = Σ (live% − ref%) · ln(live% / ref%)``) with the same
industry-standard thresholds the calibration monitor uses
(``PSI_WATCH = 0.10``, ``PSI_ALERT = 0.25``): one drift language across
the whole gate.

:meth:`fit_reference` snapshots the reference window;
:meth:`observe` compares a live window and returns an
:class:`AdaptiveDriftReport` with per-signal PSI, severity, and an
actionable advisory. Empty windows are refused — drift over nothing is
not "no drift", it's "no data".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from hugrgate.errors import SpecError

from hugrgate.adaptive.telemetry import RouteEvent
from hugrgate.drift import (
    PSI_ALERT,
    PSI_WATCH,
    DriftReport,
    population_stability_index,
    recalibration_advisory,
)

__all__ = [
    "AdaptiveDriftReport",
    "AdaptiveRouteDriftDetector",
]


def _route_shares(events: List[RouteEvent], arms: List[str]) -> List[float]:
    counts = {arm: 0 for arm in arms}
    for event in events:
        if event.chosen in counts:
            counts[event.chosen] += 1
    total = len(events)
    return [counts[arm] / total for arm in arms]


def _reward_histogram(events: List[RouteEvent],
                      n_bins: int = 10) -> List[float]:
    counts = [0] * n_bins
    usable = 0
    for event in events:
        quality = event.quality
        if quality is None:
            continue
        idx = min(int(quality * n_bins), n_bins - 1)
        counts[idx] += 1
        usable += 1
    if usable == 0:
        return [0.0] * n_bins
    return [c / usable for c in counts]


@dataclass(frozen=True)
class AdaptiveDriftReport:
    """One drift observation over route shares and rewards."""

    psi_route: float
    psi_reward: float
    severity: str  # "none" | "watch" | "action"
    n_reference: int
    n_live: int
    arms: List[str] = field(default_factory=list)
    advisory: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "psi_route": self.psi_route,
            "psi_reward": self.psi_reward,
            "severity": self.severity,
            "n_reference": self.n_reference,
            "n_live": self.n_live,
            "arms": list(self.arms),
            "advisory": self.advisory,
        }


class AdaptiveRouteDriftDetector:
    """PSI-based drift detection for route shares and rewards."""

    def __init__(self, *, watch_threshold: float = PSI_WATCH,
                 alert_threshold: float = PSI_ALERT,
                 reward_bins: int = 10) -> None:
        if not 0 < watch_threshold < alert_threshold:
            raise SpecError(
                "need 0 < watch_threshold < alert_threshold, got "
                f"{watch_threshold}, {alert_threshold}")
        if reward_bins < 2:
            raise SpecError(f"reward_bins must be >= 2, got {reward_bins}")
        self.watch_threshold = watch_threshold
        self.alert_threshold = alert_threshold
        self.reward_bins = reward_bins
        self._reference: Optional[List[RouteEvent]] = None
        self._arms: List[str] = []

    @property
    def has_reference(self) -> bool:
        return self._reference is not None

    def fit_reference(self, events: Iterable[RouteEvent]) -> int:
        """Snapshot the reference window. Returns event count."""
        events = [e for e in events if not e.shadow]
        if not events:
            raise SpecError(
                "drift reference needs at least one non-shadow event")
        self._reference = events
        self._arms = sorted({e.chosen for e in events})
        return len(events)

    def observe(self, events: Iterable[RouteEvent]) -> AdaptiveDriftReport:
        """Compare a live window against the reference."""
        if self._reference is None:
            raise SpecError(
                "no reference fitted: call fit_reference() first")
        assert self._reference is not None
        live = [e for e in events if not e.shadow]
        if not live:
            raise SpecError("drift observation needs at least one live event")
        ref = self._reference
        arms = sorted(set(self._arms) | {e.chosen for e in live})

        psi_route = population_stability_index(
            _route_shares(ref, arms), _route_shares(live, arms))
        psi_reward = population_stability_index(
            _reward_histogram(ref, self.reward_bins),
            _reward_histogram(live, self.reward_bins))

        worst = max(psi_route, psi_reward)
        if worst >= self.alert_threshold:
            severity = "action"
        elif worst >= self.watch_threshold:
            severity = "watch"
        else:
            severity = "none"

        if severity == "action":
            calib = recalibration_advisory(DriftReport(
                psi=worst, alert=True, severity="action",
                n_reference=len(ref), n_live=len(live),
                n_bins=self.reward_bins))
            advisory = (
                f"ACTION: route/reward drift detected "
                f"(psi_route={psi_route:.3f}, psi_reward={psi_reward:.3f}). "
                f"Consider retraining the offline policy (slice 131), "
                f"checking counterfactual value (slice 144), and rolling "
                f"back (slice 145) if a recent promotion caused it. "
                f"Calibration desk says: {calib['message']}")
        elif severity == "watch":
            advisory = (
                f"WATCH: mild drift (psi_route={psi_route:.3f}, "
                f"psi_reward={psi_reward:.3f}); keep observing, no action "
                f"required yet.")
        else:
            advisory = (
                f"No significant drift (psi_route={psi_route:.3f}, "
                f"psi_reward={psi_reward:.3f}).")

        return AdaptiveDriftReport(
            psi_route=psi_route,
            psi_reward=psi_reward,
            severity=severity,
            n_reference=len(ref),
            n_live=len(live),
            arms=arms,
            advisory=advisory,
        )
