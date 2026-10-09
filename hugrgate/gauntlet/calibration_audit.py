"""Calibration truth audit (slice 494).

The calibration metrics (``expected_calibration_error`` et al.)
are only as trustworthy as their agreement with ground truth.
This module audits the ECE metric itself against synthetic data
with *known* true probabilities:

- a perfect forecaster (reports the true p) must score ECE near
  zero — within statistical noise;
- a deliberately miscalibrated forecaster (overconfidence map
  ``q = clip(0.5 + s*(p - 0.5))``) must score clearly above zero;
- ECE must grow monotonically with the miscalibration severity
  ``s`` — the metric is sensitive, not just thresholded.

All randomness is seeded; reruns are bit-identical.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

import numpy as np

from hugrgate.calibration.metrics import (
    expected_calibration_error,
    reliability_diagram,
)

__all__ = [
    "CalibrationAuditReport",
    "overconfidence_map",
    "run_calibration_audit",
    "synthetic_bernoulli",
]


def synthetic_bernoulli(n: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Draw true probabilities ``p ~ U(0, 1)`` and labels ``y ~ Bern(p)``."""
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.0, 1.0, size=n)
    y = (rng.uniform(0.0, 1.0, size=n) < p).astype(int)
    return p, y


def overconfidence_map(severity: float) -> Callable[[np.ndarray], np.ndarray]:
    """Miscalibration map: push probabilities away from 0.5.

    ``s = 1`` is the identity (perfect); larger ``s`` is more
    overconfident. Output is clipped to [0, 1].
    """
    def _map(p: np.ndarray) -> np.ndarray:
        return np.clip(0.5 + severity * (p - 0.5), 0.0, 1.0)

    return _map


@dataclass
class CalibrationAuditReport:
    """Outcome of :func:`run_calibration_audit`."""

    n: int
    n_bins: int
    seed: int
    ece_perfect: float
    ece_by_severity: dict[float, float] = field(default_factory=dict)
    perfect_bins: list[dict[str, Any]] = field(default_factory=list)
    tolerance: float = 0.03
    min_miscalibrated_ece: float = 0.04

    @property
    def perfect_within_noise(self) -> bool:
        return self.ece_perfect < self.tolerance

    @property
    def miscalibration_detected(self) -> bool:
        bad = [s for s in self.ece_by_severity if s > 1.0]
        return bool(bad) and all(
            self.ece_by_severity[s] > self.min_miscalibrated_ece
            for s in bad)

    @property
    def monotone(self) -> bool:
        ordered = [self.ece_by_severity[s]
                   for s in sorted(self.ece_by_severity)]
        return all(b >= a for a, b in pairwise(ordered))

    @property
    def passed(self) -> bool:
        return (self.perfect_within_noise
                and self.miscalibration_detected
                and self.monotone)

    def to_markdown(self) -> str:
        lines = [
            "# Calibration truth audit",
            "",
            f"n={self.n}, bins={self.n_bins}, seed={self.seed}",
            "",
            "| forecaster | ECE |",
            "|---|---|",
            f"| perfect (true p) | {self.ece_perfect:.4f} |",
        ]
        for sev in sorted(self.ece_by_severity):
            lines.append(f"| overconfidence s={sev} | "
                         f"{self.ece_by_severity[sev]:.4f} |")
        lines += [
            "",
            f"tolerance (perfect): < {self.tolerance}",
            f"minimum (miscalibrated): > {self.min_miscalibrated_ece}",
            f"monotone in severity: {self.monotone}",
            "",
            f"**Verdict: {'PASS' if self.passed else 'FAIL'}**",
            "",
        ]
        return "\n".join(lines)


def run_calibration_audit(n: int = 20_000,
                          n_bins: int = 15,
                          seed: int = 494,
                          severities: tuple[float, ...] = (1.0, 1.25, 1.5),
                          ) -> CalibrationAuditReport:
    """Audit ECE against synthetic known-probability data."""
    p_true, y = synthetic_bernoulli(n, seed)
    y_list = [int(v) for v in y]
    p_list = [float(v) for v in p_true]
    ece_perfect = expected_calibration_error(y_list, p_list, n_bins)
    ece_by_severity: dict[float, float] = {}
    for sev in severities:
        q = [float(v) for v in overconfidence_map(sev)(p_true)]
        ece_by_severity[sev] = expected_calibration_error(y_list, q, n_bins)
    bins = reliability_diagram(y_list, p_list, n_bins)
    return CalibrationAuditReport(
        n=n, n_bins=n_bins, seed=seed,
        ece_perfect=ece_perfect,
        ece_by_severity=ece_by_severity,
        perfect_bins=[dict(b) for b in bins],
    )
