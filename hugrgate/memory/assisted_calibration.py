"""Memory-assisted calibration. Slice 322.

Models are often miscalibrated; memory knows by how much. This
module fits an empirical recalibration map from labeled episodes:
bin predicted probabilities, measure the observed positive rate per
bin, and run PAVA (pool adjacent violators) isotonic regression so
the corrected curve is monotone. :func:`assess_calibration` splits
episodes chronologically (70% fit / 30% validate) and reports ECE
and Brier score before and after correction on the held-out set —
the statistical validation this slice requires.

Metric/coverage assumptions (stated, not hidden):

- labels come from attached outcomes via ``Outcome.is_positive()``
  (success, or partial with score >= 0.5);
- bins are equal-width over [0, 1]; empty bins are dropped before
  PAVA and the map interpolates across them;
- ``correct()`` is piecewise-linear between bin centers, clamped to
  [0, 1], constant outside the observed range;
- the chronological split assumes the miscalibration is stationary;
  under distribution shift, refit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hugrgate.errors import MemoryError
from hugrgate.memory.query import MemoryQuery
from hugrgate.memory.types import EpisodeLike, HistoryLike

__all__ = [
    "CalibrationMap",
    "CalibrationValidation",
    "assess_calibration",
    "brier_score",
    "calibrate_from_memory",
    "expected_calibration_error",
]


def _pava(y: list[float], w: list[float]) -> list[float]:
    """Isotonic (non-decreasing) regression via pool adjacent violators.

    ``y`` values, ``w`` positive weights; returns fitted values aligned
    with the input order.
    """
    blocks: list[list[float]] = []  # [sum_wy, sum_w, count]
    for yi, wi in zip(y, w, strict=True):
        blocks.append([yi * wi, wi, 1.0])
        while len(blocks) >= 2:
            first, second = blocks[-2], blocks[-1]
            if first[0] / first[1] <= second[0] / second[1]:
                break
            merged = [first[0] + second[0], first[1] + second[1],
                      first[2] + second[2]]
            blocks[-2:] = [merged]
    out: list[float] = []
    for sum_wy, sum_w, count in blocks:
        out.extend([sum_wy / sum_w] * int(count))
    return out


def brier_score(probabilities: list[float], labels: list[int]) -> float:
    """Mean squared error between probabilities and 0/1 labels."""
    if len(probabilities) != len(labels):
        raise ValueError("probabilities and labels must align")
    if not probabilities:
        raise ValueError("brier_score needs at least one sample")
    return sum((p - y) ** 2 for p, y in
               zip(probabilities, labels, strict=True)) / len(probabilities)


def expected_calibration_error(probabilities: list[float],
                               labels: list[int],
                               n_bins: int = 10) -> float:
    """ECE with equal-width bins: sum |acc - conf| * bin_weight."""
    if n_bins < 1:
        raise ValueError(f"n_bins must be >= 1, got {n_bins}")
    if len(probabilities) != len(labels):
        raise ValueError("probabilities and labels must align")
    if not probabilities:
        return 0.0
    ece = 0.0
    n = len(probabilities)
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        idx = [i for i, p in enumerate(probabilities)
               if (lo <= p < hi) or (b == n_bins - 1 and p == 1.0)]
        if not idx:
            continue
        acc = sum(labels[i] for i in idx) / len(idx)
        conf = sum(probabilities[i] for i in idx) / len(idx)
        ece += abs(acc - conf) * len(idx) / n
    return ece


@dataclass(frozen=True)
class CalibrationMap:
    """Empirical recalibration: predicted p -> corrected p."""

    bin_centers: tuple[float, ...]
    corrected: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.bin_centers) != len(self.corrected):
            raise ValueError("bin_centers and corrected must align")
        if not self.bin_centers:
            raise ValueError("CalibrationMap needs at least one bin")
        if any(not 0.0 <= c <= 1.0 for c in self.corrected):
            raise ValueError("corrected values must be in [0, 1]")

    def correct(self, p: float) -> float:
        """Recalibrated probability for a predicted ``p``."""
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"p must be in [0, 1], got {p}")
        centers = self.bin_centers
        values = self.corrected
        if p <= centers[0]:
            return values[0]
        if p >= centers[-1]:
            return values[-1]
        for i in range(1, len(centers)):
            if p <= centers[i]:
                lo_c, hi_c = centers[i - 1], centers[i]
                lo_v, hi_v = values[i - 1], values[i]
                if hi_c == lo_c:
                    return lo_v
                t = (p - lo_c) / (hi_c - lo_c)
                return min(1.0, max(0.0, lo_v + t * (hi_v - lo_v)))
        return values[-1]  # unreachable, but total

    def to_dict(self) -> dict[str, Any]:
        return {
            "bin_centers": list(self.bin_centers),
            "corrected": list(self.corrected),
        }


@dataclass(frozen=True)
class CalibrationValidation:
    """Held-out validation of a calibration map."""

    n_fit: int
    n_validate: int
    ece_before: float
    ece_after: float
    brier_before: float
    brier_after: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_fit": self.n_fit,
            "n_validate": self.n_validate,
            "ece_before": self.ece_before,
            "ece_after": self.ece_after,
            "brier_before": self.brier_before,
            "brier_after": self.brier_after,
        }


def _labeled_pairs(episodes: list[EpisodeLike]
                   ) -> list[tuple[float, int]]:
    pairs = []
    for episode in episodes:
        outcome = episode.outcome
        if outcome is None:
            continue
        pairs.append((episode.record.probability,
                      1 if outcome.is_positive() else 0))
    return pairs


def _fit_map(pairs: list[tuple[float, int]],
             n_bins: int) -> CalibrationMap:
    """Bin (p, label) pairs and fit a PAVA isotonic recalibration map."""
    centers: list[float] = []
    rates: list[float] = []
    weights: list[float] = []
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        in_bin = [(p, y) for p, y in pairs
                  if (lo <= p < hi) or (b == n_bins - 1 and p == 1.0)]
        if not in_bin:
            continue
        centers.append(sum(p for p, _ in in_bin) / len(in_bin))
        rates.append(sum(y for _, y in in_bin) / len(in_bin))
        weights.append(float(len(in_bin)))
    if not centers:
        raise MemoryError("no usable probability bins to fit")
    # bins are generated in probability order; PAVA enforces monotonicity
    return CalibrationMap(bin_centers=tuple(centers),
                          corrected=tuple(_pava(rates, weights)))


def calibrate_from_memory(history: HistoryLike, *,
                          n_bins: int = 10) -> CalibrationMap:
    """Fit a recalibration map on all labeled episodes in ``history``."""
    if n_bins < 1:
        raise ValueError(f"n_bins must be >= 1, got {n_bins}")
    pairs = _labeled_pairs(history.find(MemoryQuery()))
    if not pairs:
        raise MemoryError("calibrate_from_memory needs at least one "
                          "episode with an attached outcome")
    return _fit_map(pairs, n_bins)


def assess_calibration(history: HistoryLike, *,
                       n_bins: int = 10,
                       fit_fraction: float = 0.7) -> tuple[CalibrationMap,
                                                          CalibrationValidation]:
    """Fit on the oldest ``fit_fraction``; validate on the rest.

    Returns the map and held-out ECE/Brier before vs after.
    """
    if not 0.0 < fit_fraction < 1.0:
        raise ValueError(
            f"fit_fraction must be in (0, 1), got {fit_fraction}")
    episodes = sorted(history.find(MemoryQuery()),
                      key=lambda e: e.recorded_at)
    labeled = [e for e in episodes if e.outcome is not None]
    if not labeled:
        raise MemoryError("assess_calibration needs at least one "
                          "episode with an attached outcome")
    cut = max(1, int(len(labeled) * fit_fraction))
    fit_eps, val_eps = labeled[:cut], labeled[cut:]
    if not val_eps:
        raise MemoryError(
            "assess_calibration needs labeled episodes on both sides "
            "of the split")

    fit_pairs = _labeled_pairs(fit_eps)
    val_pairs = _labeled_pairs(val_eps)

    cmap = _fit_map(fit_pairs, n_bins)

    val_p = [p for p, _ in val_pairs]
    val_y = [y for _, y in val_pairs]
    corrected_p = [cmap.correct(p) for p in val_p]
    validation = CalibrationValidation(
        n_fit=len(fit_pairs),
        n_validate=len(val_pairs),
        ece_before=expected_calibration_error(val_p, val_y, n_bins),
        ece_after=expected_calibration_error(corrected_p, val_y, n_bins),
        brier_before=brier_score(val_p, val_y),
        brier_after=brier_score(corrected_p, val_y),
    )
    return cmap, validation
