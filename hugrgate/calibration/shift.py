"""Calibration under distribution shift. Slice 090.

Two shift flavors, two tools:

**Covariate shift** (``P(x)`` changes, ``P(y|x)`` doesn't): detect it with
the population stability index (:func:`psi`), then correct with binned
density-ratio weights (:func:`density_ratio_weights`) and
:func:`resample_for_shift`, which resamples the source fit set so it mimics
the target covariate distribution before fitting.

**Label shift** (``P(y)`` changes, ``P(x|y)`` doesn't): estimate the target
prior with the Saerens-Latinne-Decaestecker EM algorithm
(:func:`em_target_prior`), then transport with the slice-089
:func:`~hugrgate.calibration.imbalance.saerens_prior_correction`.

All density estimates are binned histograms over the score axis - honest,
dependency-free, and adequate for one-dimensional calibration scores.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

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
from hugrgate.calibration.imbalance import saerens_prior_correction
from hugrgate.errors import CalibrationError

__all__ = [
    "density_ratio_weights",
    "em_target_prior",
    "psi",
    "psi_band",
    "resample_for_shift",
]


def _histograms(source: np.ndarray, target: np.ndarray,
                n_bins: int, smooth: float) -> tuple[np.ndarray, np.ndarray,
                                                    np.ndarray]:
    lo = float(min(source.min(), target.min()))
    hi = float(max(source.max(), target.max()))
    if hi <= lo:
        hi = lo + 1.0
    edges = np.linspace(lo, hi, n_bins + 1)
    s_counts, _ = np.histogram(source, bins=edges)
    t_counts, _ = np.histogram(target, bins=edges)
    s = (s_counts + smooth) / (s_counts.sum() + smooth * n_bins)
    t = (t_counts + smooth) / (t_counts.sum() + smooth * n_bins)
    return s, t, edges


def psi(source: Sequence[float], target: Sequence[float],
        n_bins: int = 10, smooth: float = 0.5) -> float:
    """Population stability index between source and target score samples."""
    _require_numpy()
    s = np.asarray(list(source), dtype=float)
    t = np.asarray(list(target), dtype=float)
    if s.size == 0 or t.size == 0:
        raise CalibrationError("psi needs non-empty samples")
    if n_bins < 2:
        raise CalibrationError("n_bins must be ≥ 2")
    ps, pt, _ = _histograms(s, t, n_bins, smooth)
    return float(np.sum((pt - ps) * np.log(pt / ps)))


def psi_band(value: float) -> str:
    """Standard PSI interpretation bands."""
    if value < 0.1:
        return "no significant change"
    if value < 0.25:
        return "moderate change"
    return "significant change"


def density_ratio_weights(source: Sequence[float],
                          target: Sequence[float],
                          n_bins: int = 10,
                          smooth: float = 0.5) -> list[float]:
    """Importance weight per source point: ``p_target(bin) / p_source(bin)``.

    Weights are normalized to mean 1.  Under pure covariate shift, fitting
    with these weights (or resampling by them) targets the target
    distribution.
    """
    _require_numpy()
    s = np.asarray(list(source), dtype=float)
    t = np.asarray(list(target), dtype=float)
    if s.size == 0 or t.size == 0:
        raise CalibrationError("need non-empty samples")
    ps, pt, edges = _histograms(s, t, n_bins, smooth)
    ratio = pt / ps
    idx = np.clip(np.digitize(s, edges[1:-1]), 0, n_bins - 1)
    w = ratio[idx]
    return (w / w.mean()).tolist()


def resample_for_shift(source_scores: Sequence[float],
                       source_labels: Sequence[int],
                       target_scores: Sequence[float],
                       n_bins: int = 10, seed: int = 0
                       ) -> tuple[list[float], list[int]]:
    """Resample the source fit set to mimic the target covariate mix."""
    _require_numpy()
    s = list(source_scores)
    y = list(source_labels)
    if len(s) != len(y):
        raise CalibrationError("scores/labels length mismatch")
    if not s:
        raise CalibrationError("empty source data")
    w = np.asarray(density_ratio_weights(s, list(target_scores), n_bins))
    rng = np.random.default_rng(seed)
    take = rng.choice(len(s), size=len(s), replace=True,
                      p=w / w.sum())
    return [s[i] for i in take], [y[i] for i in take]


def em_target_prior(source_scores: Sequence[float],
                    source_labels: Sequence[int],
                    target_scores: Sequence[float],
                    factory: Callable[[], Calibrator],
                    max_iter: int = 100,
                    tol: float = 1e-6) -> float:
    """Saerens EM estimate of the target positive rate (label shift).

    Fits the calibrator on the source data, scores the (unlabeled) target
    sample, then iterates the prior until the mean corrected posterior
    stops moving.
    """
    _require_numpy()
    probe = factory()
    if not isinstance(probe, Calibrator):
        raise CalibrationError("factory must return a Calibrator")
    s = list(source_scores)
    y = list(source_labels)
    t = list(target_scores)
    if not s or not t:
        raise CalibrationError("need non-empty samples")
    cal = factory().fit(s, y)
    p_t = [cal.calibrate(float(v)) for v in t]
    fit_prior = sum(y) / len(y)
    if fit_prior in (0.0, 1.0):
        raise CalibrationError("source needs both classes for EM")
    prior = fit_prior
    for _ in range(max_iter):
        corrected = [saerens_prior_correction(p, fit_prior, prior)
                     for p in p_t]
        new_prior = float(sum(corrected) / len(corrected))
        if abs(new_prior - prior) < tol:
            prior = new_prior
            break
        prior = new_prior
    return float(min(1.0, max(0.0, prior)))
