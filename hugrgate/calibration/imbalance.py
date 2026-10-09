"""Calibration under class imbalance. Slice 089.

Heavy imbalance breaks naive calibration two ways: the fit is dominated by
the majority class, and the deployment prior often differs from the fit
prior anyway.  This module provides the standard, honest toolkit:

- :func:`rebalance` - resample a fit set to a target positive rate
  (minority oversampling / majority undersampling, seeded);
- :func:`saerens_prior_correction` - Saerens-Latinne-Decaestecker prior
  correction: transport calibrated probabilities from the fit prior to the
  deployment prior without refitting;
- :func:`fit_balanced` - rebalance + fit any :class:`Calibrator`, returning
  the fitted unit and an :class:`ImbalanceReport`;
- :func:`stratified_metrics` - Brier/ECE computed separately on the
  positive and negative strata, so minority-class miscalibration can't hide
  behind a good-looking average.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from typing import Any

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
    "ImbalanceReport",
    "fit_balanced",
    "rebalance",
    "saerens_prior_correction",
    "stratified_metrics",
]


@dataclass
class ImbalanceReport:
    """What the imbalance adapter did, in JSON-serializable form."""

    base_rate: float
    target_rate: float
    n_before: int
    n_after: int
    correction_applied: bool
    deploy_prior: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def rebalance(scores: Sequence[float], labels: Sequence[int],
              target_rate: float = 0.5,
              seed: int = 0) -> tuple[list[float], list[int]]:
    """Resample to ``target_rate`` positives (seeded, with replacement)."""
    _require_numpy()
    if not 0.0 < target_rate < 1.0:
        raise CalibrationError("target_rate must be in (0, 1)")
    s = np.asarray(list(scores), dtype=float)
    y = np.asarray(list(labels), dtype=int)
    if s.shape != y.shape:
        raise CalibrationError("scores/labels length mismatch")
    if s.size == 0:
        raise CalibrationError("cannot rebalance empty data")
    pos_idx = np.flatnonzero(y == 1)
    neg_idx = np.flatnonzero(y == 0)
    if pos_idx.size == 0 or neg_idx.size == 0:
        raise CalibrationError("rebalance needs both classes")
    rng = np.random.default_rng(seed)
    n = s.size
    n_pos = round(n * target_rate)
    n_neg = n - n_pos
    take_pos = rng.choice(pos_idx, size=n_pos, replace=True)
    take_neg = rng.choice(neg_idx, size=n_neg, replace=True)
    order = rng.permutation(n)
    take = np.concatenate([take_pos, take_neg])[order]
    return s[take].tolist(), y[take].tolist()


def saerens_prior_correction(p_cal: float, fit_prior: float,
                             deploy_prior: float) -> float:
    """Transport a calibrated probability to a new class prior.

    ``p_cal`` was calibrated under ``fit_prior = P(y=1)``; the deployment
    population has ``deploy_prior``.  Returns the corrected probability.
    Identity when the priors match.
    """
    for name, v in (("p_cal", p_cal), ("fit_prior", fit_prior),
                    ("deploy_prior", deploy_prior)):
        if not 0.0 <= v <= 1.0:
            raise CalibrationError(f"{name} must be in [0, 1]")
    if fit_prior in (0.0, 1.0) or deploy_prior in (0.0, 1.0):
        raise CalibrationError("priors must be strictly inside (0, 1)")
    w1 = deploy_prior / fit_prior
    w0 = (1.0 - deploy_prior) / (1.0 - fit_prior)
    num = p_cal * w1
    den = num + (1.0 - p_cal) * w0
    return float(num / den) if den > 0 else 0.0


def fit_balanced(factory: Callable[[], Calibrator],
                 scores: Sequence[float], labels: Sequence[int],
                 target_rate: float = 0.5, seed: int = 0,
                 deploy_prior: float | None = None) -> tuple[Calibrator,
                                                             ImbalanceReport]:
    """Rebalance the fit set, fit the calibrator, record what was done.

    If ``deploy_prior`` is given, the report notes that
    :func:`saerens_prior_correction` should be applied at serving time
    (the calibrator itself stays prior-agnostic).
    """
    probe = factory()
    if not isinstance(probe, Calibrator):
        raise CalibrationError("factory must return a Calibrator")
    scores = list(scores)
    labels = list(labels)
    base_rate = sum(labels) / len(labels) if labels else 0.0
    rs, ry = rebalance(scores, labels, target_rate, seed)
    cal = factory()
    cal.fit(rs, ry)
    report = ImbalanceReport(
        base_rate=float(base_rate),
        target_rate=float(target_rate),
        n_before=len(scores),
        n_after=len(rs),
        correction_applied=deploy_prior is not None,
        deploy_prior=float(deploy_prior) if deploy_prior is not None
        else float(base_rate),
    )
    return cal, report


def stratified_metrics(y_true: Sequence[int], y_prob: Sequence[float],
                       n_bins: int = 10) -> dict[str, dict[str, float]]:
    """Brier/ECE on the positive and negative strata separately."""
    _require_numpy()
    y = np.asarray(list(y_true), dtype=float)
    p = np.asarray(list(y_prob), dtype=float)
    if y.shape != p.shape:
        raise CalibrationError("length mismatch")
    if y.size == 0:
        raise CalibrationError("empty inputs")
    out: dict[str, dict[str, float]] = {}
    for name, mask in (("positive", y == 1.0), ("negative", y == 0.0)):
        ys, ps = y[mask].astype(int).tolist(), p[mask].tolist()
        if not ys:
            out[name] = {"n": 0.0, "brier": float("nan"),
                         "ece": float("nan")}
        else:
            out[name] = {
                "n": float(len(ys)),
                "brier": brier_score(ys, ps),
                "ece": expected_calibration_error(ys, ps, n_bins),
            }
    out["overall"] = {
        "n": float(y.size),
        "brier": brier_score(y.astype(int).tolist(), p.tolist()),
        "ece": expected_calibration_error(y.astype(int).tolist(),
                                          p.tolist(), n_bins),
    }
    return out
