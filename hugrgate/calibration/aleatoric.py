"""Aleatoric uncertainty adapters. Slice 096.

Aleatoric uncertainty = noise inherent in the data-generating process: no
amount of modeling removes it.  These adapters *estimate* it from
observables:

- :func:`predictive_entropy` — entropy of one predictive distribution
  (with a single model, the working aleatoric estimate);
- :func:`bernoulli_noise` — ``p(1−p)``, the variance of a Bernoulli
  outcome: the irreducible noise at calibrated probability ``p``;
- :func:`label_noise_estimate` — binned ``E[p(1−p)]`` over a labeled fit
  set: the data's own noise floor as the calibrator sees it;
- :func:`noise_floor_report` — bundles the estimate with the per-bin
  detail into a JSON-serializable :class:`AleatoricReport`.

Companion to slice 095 (epistemic adapters): together they cover both
halves of slice 094's decomposition from measurable quantities.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Sequence

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

from hugrgate.errors import CalibrationError

__all__ = [
    "AleatoricReport",
    "predictive_entropy",
    "bernoulli_noise",
    "label_noise_estimate",
    "noise_floor_report",
]

_EPS = 1e-15


@dataclass
class AleatoricReport:
    """One adapter's aleatoric estimate, JSON-serializable."""

    adapter: str
    value: float
    details: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def predictive_entropy(proba: Mapping[str, float]) -> float:
    """Entropy (nats) of a predictive distribution."""
    _require_numpy()
    vals = np.array([float(v) for v in proba.values()], dtype=float)
    if vals.size == 0:
        raise CalibrationError("empty distribution")
    if np.any(~np.isfinite(vals)) or np.any(vals < 0):
        raise CalibrationError("probabilities must be finite and ≥ 0")
    total = vals.sum()
    if total <= 0:
        raise CalibrationError("probabilities must sum to something positive")
    p = np.clip(vals / total, _EPS, 1.0)
    return float(-np.sum(p * np.log(p)))


def bernoulli_noise(p: float) -> float:
    """Irreducible variance of a Bernoulli(``p``) outcome."""
    if not 0.0 <= p <= 1.0:
        raise CalibrationError("p must be in [0, 1]")
    return float(p * (1.0 - p))


def label_noise_estimate(scores: Sequence[float], labels: Sequence[int],
                         n_bins: int = 10) -> float:
    """Binned ``E[p(1−p)]``: the label noise floor visible in the fit data.

    Uses the empirical positive rate per score bin as ``p``.  A perfectly
    separable fit set gives ~0; pure noise gives ~0.25.
    """
    _require_numpy()
    s = np.asarray(list(scores), dtype=float)
    y = np.asarray(list(labels), dtype=float)
    if s.shape != y.shape or s.size == 0:
        raise CalibrationError("scores/labels must be non-empty and aligned")
    if n_bins < 1:
        raise CalibrationError("n_bins must be ≥ 1")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(np.clip(s, 0.0, 1.0), edges[1:-1]), 0, n_bins - 1)
    total = 0.0
    for b in range(n_bins):
        mask = idx == b
        n = int(mask.sum())
        if n == 0:
            continue
        p = float(y[mask].mean())
        total += (n / s.size) * p * (1.0 - p)
    return float(total)


def noise_floor_report(scores: Sequence[float], labels: Sequence[int],
                       n_bins: int = 10) -> AleatoricReport:
    """Full noise-floor report with per-bin detail."""
    _require_numpy()
    s = np.asarray(list(scores), dtype=float)
    y = np.asarray(list(labels), dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(np.clip(s, 0.0, 1.0), edges[1:-1]), 0, n_bins - 1)
    bins: List[Dict[str, float]] = []
    for b in range(n_bins):
        mask = idx == b
        n = int(mask.sum())
        p = float(y[mask].mean()) if n else 0.0
        bins.append({"bin": float(b), "n": float(n),
                     "positive_rate": p, "noise": p * (1.0 - p)})
    return AleatoricReport(
        adapter="label-noise",
        value=label_noise_estimate(scores, labels, n_bins),
        details={"n_bins": n_bins, "bins": bins,
                 "n_samples": int(s.size)},
    )
