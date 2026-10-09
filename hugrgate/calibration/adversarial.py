"""Calibration adversarial tests. Slice 098.

Calibration is usually evaluated on the same distribution it was fit on —
the kindest possible test.  This module attacks it instead:

- :func:`overconfidence_attack` — pushes scores toward the extremes
  (the classic "model gets cocky" failure);
- :func:`underconfidence_attack` — pulls scores toward 0.5;
- :func:`label_flip_attack` — random label noise (seeded);
- :func:`bias_shift_attack` — systematic additive score bias, clipped;
- :func:`stress_test` — fits a calibrator on clean data, then reports
  Brier/ECE degradation under each attack in a JSON-serializable
  :class:`StressReport`.

Use it in CI or before promoting a calibration profile: a map that
collapses under mild attacks shouldn't ship.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Sequence

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

from hugrgate.calibration._base import Calibrator
from hugrgate.calibration.metrics import (
    brier_score,
    expected_calibration_error,
)
from hugrgate.errors import CalibrationError

__all__ = [
    "StressReport",
    "overconfidence_attack",
    "underconfidence_attack",
    "label_flip_attack",
    "bias_shift_attack",
    "stress_test",
]


def _as_arrays(scores: Sequence[float],
               labels: Sequence[int]) -> tuple[np.ndarray, np.ndarray]:
    _require_numpy()
    s = np.asarray(list(scores), dtype=float)
    y = np.asarray(list(labels), dtype=float)
    if s.shape != y.shape or s.size == 0:
        raise CalibrationError("scores/labels must be non-empty and aligned")
    if np.any(~np.isfinite(s)):
        raise CalibrationError("scores must be finite")
    return s, y


def overconfidence_attack(scores: Sequence[float],
                          strength: float = 0.2) -> List[float]:
    """Push scores away from 0.5 by ``strength`` (clipped to [0, 1])."""
    if not 0.0 <= strength <= 1.0:
        raise CalibrationError("strength must be in [0, 1]")
    s, _ = _as_arrays(scores, [0] * len(list(scores)))
    out = 0.5 + (s - 0.5) * (1.0 + strength)
    return np.clip(out, 0.0, 1.0).tolist()


def underconfidence_attack(scores: Sequence[float],
                           strength: float = 0.2) -> List[float]:
    """Pull scores toward 0.5 by ``strength``."""
    if not 0.0 <= strength <= 1.0:
        raise CalibrationError("strength must be in [0, 1]")
    s, _ = _as_arrays(scores, [0] * len(list(scores)))
    out = s + (0.5 - s) * strength
    return np.clip(out, 0.0, 1.0).tolist()


def label_flip_attack(labels: Sequence[int], flip_rate: float = 0.1,
                      seed: int = 0) -> List[int]:
    """Flip each label independently with probability ``flip_rate``."""
    if not 0.0 <= flip_rate <= 1.0:
        raise CalibrationError("flip_rate must be in [0, 1]")
    y = list(labels)
    if any(v not in (0, 1) for v in y):
        raise CalibrationError("labels must be 0/1")
    rng = np.random.default_rng(seed)
    flips = rng.random(len(y)) < flip_rate
    return [1 - v if f else v for v, f in zip(y, flips)]


def bias_shift_attack(scores: Sequence[float],
                      shift: float = 0.1) -> List[float]:
    """Add a systematic bias to every score (clipped to [0, 1])."""
    if not -1.0 <= shift <= 1.0:
        raise CalibrationError("shift must be in [-1, 1]")
    s, _ = _as_arrays(scores, [0] * len(list(scores)))
    return np.clip(s + shift, 0.0, 1.0).tolist()


@dataclass
class StressReport:
    """Per-attack degradation of one fitted calibrator."""

    calibrator_name: str
    baseline: Dict[str, float]
    attacks: List[Dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def worst_ece_degradation(self) -> float:
        if not self.attacks:
            return 0.0
        return max(a["ece_after"] - a["ece_before"] for a in self.attacks)


def stress_test(factory: Callable[[], Calibrator],
                scores: Sequence[float], labels: Sequence[int],
                attacks: Dict[str, Callable[[List[float], List[int]],
                                            tuple[List[float], List[int]]]]
                | None = None,
                n_bins: int = 10) -> StressReport:
    """Fit on clean data; measure degradation under each attack."""
    probe = factory()
    if not isinstance(probe, Calibrator):
        raise CalibrationError("factory must return a Calibrator")
    s = list(scores)
    y = [int(v) for v in labels]
    cal = factory().fit(s, y)
    clean = [cal.calibrate(float(v)) for v in s]
    baseline = {"brier": brier_score(y, clean),
                "ece": expected_calibration_error(y, clean, n_bins)}
    if attacks is None:
        attacks = {
            "overconfidence-0.3": lambda ss, yy: (
                overconfidence_attack(ss, 0.3), yy),
            "underconfidence-0.3": lambda ss, yy: (
                underconfidence_attack(ss, 0.3), yy),
            "label-flip-0.1": lambda ss, yy: (
                ss, label_flip_attack(yy, 0.1, seed=0)),
            "bias-shift-+0.1": lambda ss, yy: (
                bias_shift_attack(ss, 0.1), yy),
            "bias-shift--0.1": lambda ss, yy: (
                bias_shift_attack(ss, -0.1), yy),
        }
    report = StressReport(calibrator_name=cal.name, baseline=baseline)
    for name, attack in attacks.items():
        a_scores, a_labels = attack(s, y)
        a_cal = [cal.calibrate(float(v)) for v in a_scores]
        brier = brier_score(a_labels, a_cal)
        ece = expected_calibration_error(a_labels, a_cal, n_bins)
        report.attacks.append({
            "name": name,
            "brier_before": baseline["brier"],
            "brier_after": brier,
            "brier_degradation": brier - baseline["brier"],
            "ece_before": baseline["ece"],
            "ece_after": ece,
            "ece_degradation": ece - baseline["ece"],
        })
    return report
