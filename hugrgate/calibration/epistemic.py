"""Epistemic uncertainty adapters. Slice 095.

Epistemic uncertainty = "the model doesn't know what it doesn't know".
These adapters *produce* epistemic estimates from HugrGate components and
wire them into the existing abstention machinery:

- :func:`ensemble_epistemic` — mutual information across an ensemble's
  predictive distributions (slice 094's decomposition);
- :func:`distance_epistemic` — out-of-distribution proxy: how far a score
  sits from the calibration fit-score cloud, normalized to [0, 1];
- :func:`combine_epistemic` — conservative (max) combination of adapters;
- :func:`review_on_epistemic` — marks a
  :class:`~hugrgate.result.DecisionResult` for human review via
  :func:`hugrgate.abstain.mark_for_review` when epistemic uncertainty
  exceeds a threshold.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Mapping, Sequence

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency
    np = None  # type: ignore[assignment]


def _require_numpy() -> None:
    """Deliberate error when the optional numpy dependency is absent."""
    if np is None:  # pragma: no cover - optional dependency
        raise CalibrationError(
            "numpy is required for calibration; install the 'ml' extra: pip install 'hugrgate[ml]'"
        )

from hugrgate.abstain import mark_for_review
from hugrgate.calibration.decomposition import (
    UncertaintyBreakdown,
    decompose,
    decompose_dicts,
)
from hugrgate.errors import CalibrationError
from hugrgate.result import DecisionResult

__all__ = [
    "EpistemicReport",
    "ensemble_epistemic",
    "distance_epistemic",
    "combine_epistemic",
    "review_on_epistemic",
]


@dataclass
class EpistemicReport:
    """One adapter's epistemic estimate, JSON-serializable."""

    adapter: str
    value: float  # in [0, 1]-ish scale; documented per adapter
    threshold: float
    triggered: bool
    details: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def ensemble_epistemic(
        predictions: Sequence[Sequence[float]]) -> UncertaintyBreakdown:
    """Mutual-information epistemic term across ensemble members."""
    return decompose(predictions)


def ensemble_epistemic_dicts(
        predictions: Sequence[Mapping[str, float]]) -> UncertaintyBreakdown:
    """Dict-distribution variant of :func:`ensemble_epistemic`."""
    return decompose_dicts(predictions)


def distance_epistemic(score: float,
                       fit_scores: Sequence[float]) -> float:
    """OOD proxy: normalized distance of ``score`` from the fit-score cloud.

    0 when the score sits inside the seen range, rising toward 1 as it moves
    away (scaled by the cloud's own range).  A score far from anything the
    calibrator was fit on deserves epistemic suspicion.
    """
    _require_numpy()
    if not np.isfinite(float(score)):
        raise CalibrationError("score must be finite")
    cloud = np.asarray(list(fit_scores), dtype=float)
    if cloud.size == 0:
        raise CalibrationError("need a non-empty fit-score cloud")
    if np.any(~np.isfinite(cloud)):
        raise CalibrationError("fit scores must be finite")
    lo, hi = float(cloud.min()), float(cloud.max())
    span = hi - lo
    if span <= 0:
        return 0.0 if lo <= score <= hi else 1.0
    if lo <= score <= hi:
        return 0.0
    dist = min(abs(score - lo), abs(score - hi))
    return float(min(1.0, dist / span))


def combine_epistemic(values: Sequence[float]) -> float:
    """Conservative combination: the max.  Any adapter may raise the alarm."""
    vals = [float(v) for v in values]
    if not vals:
        raise CalibrationError("need at least one epistemic value")
    if any(v < 0.0 for v in vals):
        raise CalibrationError("epistemic values must be non-negative")
    return float(max(vals))


def review_on_epistemic(result: DecisionResult, epistemic_value: float,
                        threshold: float,
                        reason: str = "high-epistemic-uncertainty"
                        ) -> tuple["DecisionResult", EpistemicReport]:
    """Mark ``result`` for review when epistemic uncertainty is too high.

    Returns ``(result, report)`` — the result is the review-flagged copy
    when triggered, otherwise the original object untouched.
    """
    if threshold < 0:
        raise CalibrationError("threshold must be non-negative")
    triggered = bool(epistemic_value > threshold)
    out = (mark_for_review(result, reason,
                           reviewer="calibration-epistemic-gate")
           if triggered else result)
    return out, EpistemicReport(
        adapter="review-gate",
        value=float(epistemic_value),
        threshold=float(threshold),
        triggered=triggered,
        details={"reason": reason, "review": triggered},
    )
