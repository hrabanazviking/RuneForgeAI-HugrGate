"""Uncertainty decomposition. Slice 094.

Total predictive uncertainty splits into two principled parts (Depeweg et
al.; Kendall & Gal):

- **aleatoric** — expected entropy of the members: noise inherent in the
  data, irreducible by more modeling;
- **epistemic** — mutual information between the prediction and the model
  identity: disagreement *between* members, reducible with more data or
  better models;

with ``total = entropy(mean distribution) = aleatoric + epistemic``.

:func:`decompose` takes an ensemble's predictive distributions (one
probability vector per member) and returns an :class:`UncertaintyBreakdown`.
Feed it members' calibrated outputs — e.g. per-class vectors from
:class:`~hugrgate.calibration.perclass.PerClassCalibrator` variants or
backend ensembles — and the epistemic term tells you when the system is
guessing *about its own knowledge*.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
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

from hugrgate.errors import CalibrationError

__all__ = [
    "UncertaintyBreakdown",
    "decompose",
    "decompose_dicts",
]

_EPS = 1e-15


def _entropy(p: np.ndarray) -> float:
    pc = np.clip(p, _EPS, 1.0)
    return float(-np.sum(pc * np.log(pc)))


@dataclass
class UncertaintyBreakdown:
    """Aleatoric/epistemic split of predictive uncertainty (nats)."""

    total: float
    aleatoric: float
    epistemic: float
    n_members: int
    n_classes: int

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def decompose(predictions: Sequence[Sequence[float]]) -> UncertaintyBreakdown:
    """Decompose an ensemble's predictive distributions.

    ``predictions``: one probability vector per member (members × classes).
    """
    _require_numpy()
    mat = np.asarray([[float(v) for v in row] for row in predictions],
                     dtype=float)
    if mat.ndim != 2 or mat.shape[0] == 0 or mat.shape[1] == 0:
        raise CalibrationError("need a non-empty members × classes matrix")
    if np.any(~np.isfinite(mat)):
        raise CalibrationError("predictions must be finite")
    if np.any(mat < 0.0):
        raise CalibrationError("predictions must be non-negative")
    row_sums = mat.sum(axis=1)
    if np.any(np.abs(row_sums - 1.0) > 1e-6):
        raise CalibrationError(
            "each member distribution must sum to 1 "
            f"(got sums {row_sums.tolist()})")
    mean_dist = mat.mean(axis=0)
    total = _entropy(mean_dist)
    aleatoric = float(np.mean([_entropy(row) for row in mat]))
    epistemic = max(0.0, total - aleatoric)  # clip float dust
    return UncertaintyBreakdown(
        total=total,
        aleatoric=aleatoric,
        epistemic=epistemic,
        n_members=int(mat.shape[0]),
        n_classes=int(mat.shape[1]),
    )


def decompose_dicts(
        predictions: Sequence[Mapping[str, float]]) -> UncertaintyBreakdown:
    """Dict-distribution variant of :func:`decompose`."""
    preds = list(predictions)
    if not preds:
        raise CalibrationError("need at least one prediction")
    classes = sorted({c for d in preds for c in d})
    if not classes:
        raise CalibrationError("empty distributions")
    matrix = [[float(d.get(c, 0.0)) for c in classes] for d in preds]
    return decompose(matrix)
