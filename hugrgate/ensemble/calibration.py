"""Ensemble calibration — honest probabilities out. Slice 118.

Ensemble combination rules produce *scores*, not calibrated
probabilities: a 0.9 vote share does not mean the winner is right 90%
of the time. :class:`EnsembleCalibrator` fits temperature scaling on
held-out ensemble outputs (``p_T(v) ∝ p(v)^(1/T)``), minimizing
negative log-likelihood with a deterministic golden-section search:

- ``T > 1`` softens overconfident ensembles;
- ``T < 1`` sharpens underconfident ones;
- ``T = 1`` is the identity (a well-calibrated ensemble is left
  alone).

:func:`expected_calibration_error` mirrors the formula in
:mod:`hugrgate.bench` (10 confidence bins) but works directly on
distributions. :meth:`EnsembleCalibrator.calibrate_result` returns a
new :class:`DecisionResult` with the calibrated distribution,
``calibration_profile="ensemble:temperature"``, and the ensemble
metadata preserved.
"""

from __future__ import annotations

import math
from typing import Dict, List

from hugrgate.ensemble.base import normalized_entropy
from hugrgate.errors import BackendError, PolicyError
from hugrgate.result import DecisionResult

__all__ = [
    "expected_calibration_error",
    "EnsembleCalibrator",
]

#: Temperature search bounds. Below 0.05 the map explodes; above 10 it
#: is uniform for all practical purposes.
_T_MIN = 0.05
_T_MAX = 10.0


def expected_calibration_error(distributions: List[Dict[str, float]],
                               labels: List[str],
                               n_bins: int = 10) -> float:
    """ECE = Σ_b |acc_b − conf_b| · (n_b / n) over confidence bins."""
    if len(distributions) != len(labels):
        raise PolicyError(
            f"{len(distributions)} distributions but {len(labels)} "
            f"labels")
    if not labels:
        raise PolicyError(
            "expected_calibration_error needs labeled data")
    if n_bins < 1:
        raise PolicyError(f"n_bins must be >= 1, got {n_bins}")
    bins: List[Dict[str, float]] = [
        {"n": 0.0, "correct": 0.0, "conf": 0.0}
        for _ in range(n_bins)]
    for dist, label in zip(distributions, labels):
        if not dist:
            continue
        winner = max(dist, key=lambda k: dist[k])
        conf = dist[winner]
        b = min(int(conf * n_bins), n_bins - 1)
        bins[b]["n"] += 1
        bins[b]["conf"] += conf
        if winner == label:
            bins[b]["correct"] += 1
    n = len(labels)
    ece = 0.0
    for slot in bins:
        if slot["n"]:
            acc = slot["correct"] / slot["n"]
            avg_conf = slot["conf"] / slot["n"]
            ece += abs(acc - avg_conf) * slot["n"] / n
    return ece


def _apply_temperature(distribution: Dict[str, float],
                       temperature: float) -> Dict[str, float]:
    inv = 1.0 / temperature
    scaled = {k: p ** inv for k, p in distribution.items()}
    total = sum(scaled.values())
    if total <= 0:
        n = len(scaled)
        return {k: 1.0 / n for k in scaled}
    return {k: v / total for k, v in scaled.items()}


def _nll(distributions: List[Dict[str, float]], labels: List[str],
         temperature: float) -> float:
    total = 0.0
    for dist, label in zip(distributions, labels):
        cal = _apply_temperature(dist, temperature)
        total += -math.log(max(cal.get(label, 0.0), 1e-12))
    return total / len(distributions)


def _golden_section(distributions: List[Dict[str, float]],
                    labels: List[str]) -> float:
    """Minimize NLL over temperature in [_T_MIN, _T_MAX]."""
    gr = (math.sqrt(5) - 1) / 2
    a, b = _T_MIN, _T_MAX
    c = b - gr * (b - a)
    d = a + gr * (b - a)
    fc = _nll(distributions, labels, c)
    fd = _nll(distributions, labels, d)
    for _ in range(100):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - gr * (b - a)
            fc = _nll(distributions, labels, c)
        else:
            a, c, fc = c, d, fd
            d = a + gr * (b - a)
            fd = _nll(distributions, labels, d)
    return (a + b) / 2


class EnsembleCalibrator:
    """Temperature scaling for ensemble output distributions."""

    def __init__(self):
        self.temperature = 1.0
        self.classes: List[str] = []
        self.ece_before = math.inf
        self.ece_after = math.inf
        self.nll_before = math.inf
        self.nll_after = math.inf
        self._fitted = False

    @property
    def fitted(self) -> bool:
        return self._fitted

    def fit(self, distributions: List[Dict[str, float]],
            labels: List[str],
            classes: List[str]) -> "EnsembleCalibrator":
        """Learn the temperature on held-out ensemble outputs."""
        if len(distributions) != len(labels):
            raise PolicyError(
                f"{len(distributions)} distributions but "
                f"{len(labels)} labels")
        if not labels:
            raise PolicyError("EnsembleCalibrator.fit needs data")
        if len(set(classes)) != len(classes) or len(classes) < 2:
            raise PolicyError(
                f"classes must be ≥2 unique labels, got {classes}")
        unknown = [l for l in labels if l not in classes]
        if unknown:
            raise PolicyError(
                f"labels outside classes: {sorted(set(unknown))}")
        self.classes = list(classes)
        self.ece_before = expected_calibration_error(
            distributions, labels)
        self.nll_before = _nll(distributions, labels, 1.0)
        self.temperature = _golden_section(distributions, labels)
        self._fitted = True
        calibrated = [self.calibrate(d) for d in distributions]
        self.ece_after = expected_calibration_error(calibrated, labels)
        self.nll_after = _nll(distributions, labels, self.temperature)
        return self

    def calibrate(self, distribution: Dict[str, float]
                  ) -> Dict[str, float]:
        if not self._fitted:
            raise BackendError("EnsembleCalibrator used before fit")
        return _apply_temperature(distribution, self.temperature)

    def calibrate_result(self, result: DecisionResult
                         ) -> DecisionResult:
        """Return a calibrated copy of an ensemble result.

        Abstentions (no value) pass through unchanged — there is no
        winner to calibrate.
        """
        if not self._fitted:
            raise BackendError("EnsembleCalibrator used before fit")
        if result.value is None or not result.distribution:
            return result
        distribution = self.calibrate(result.distribution)
        key = (result.value if isinstance(result.value, str)
               else str(result.value))
        meta = dict(result.metadata)
        ens = dict(meta.get("ensemble", {}))
        ens["calibration"] = {
            "temperature": self.temperature,
            "ece_before": self.ece_before,
            "ece_after": self.ece_after,
        }
        meta["ensemble"] = ens
        return DecisionResult(
            value=result.value,
            probability=distribution.get(key, result.probability),
            distribution=distribution,
            uncertainty=normalized_entropy(distribution),
            accepted=result.accepted,
            backend=result.backend,
            model=result.model,
            latency_ms=result.latency_ms,
            calibration_profile="ensemble:temperature",
            fallback_used=result.fallback_used,
            metadata=meta,
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "temperature": self.temperature,
            "classes": list(self.classes),
            "fitted": self._fitted,
            "ece_before": self.ece_before,
            "ece_after": self.ece_after,
            "nll_before": self.nll_before,
            "nll_after": self.nll_after,
        }
