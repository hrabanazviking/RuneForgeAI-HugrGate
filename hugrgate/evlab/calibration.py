"""Calibration-method comparisons — which calibrator helps, where. Slice 361.

The calibration package (:mod:`hugrgate.calibration`) owns the
calibration *algorithms* (temperature, Platt, isotonic — numpy-based,
``ml`` extra).  This module owns the *comparison*: given a held-out
split, which method actually reduces ECE, and by how much?

- :class:`LabCalibrator` — the tiny protocol compared here:
  ``fit(confidences, correct)`` / ``calibrate(confidence)``.
- Pure-Python, base-install implementations:
  :class:`IdentityCalibrator` (the honest baseline),
  :class:`TemperatureCalibrator` (golden-section NLL fit),
  :class:`HistogramBinningCalibrator`.
- :class:`PackageCalibrator` — adapter wrapping any
  :class:`hugrgate.calibration.Calibrator`; requires numpy (the ``ml``
  extra), exactly like the package itself.
- :func:`compare_calibrators` — fit-each-on-calib, score-each-on-eval,
  rank by ECE (NLL alongside).
- :func:`compare_backend_calibration` — lab integration: evaluates
  backends once, splits pairs into calib/eval under a seed, and
  compares per backend.
"""

from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.core import HugrGate
from hugrgate.errors import Abstention, CalibrationError, EvalError
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "CalibrationComparison",
    "HistogramBinningCalibrator",
    "IdentityCalibrator",
    "LabCalibrator",
    "PackageCalibrator",
    "TemperatureCalibrator",
    "compare_backend_calibration",
    "compare_calibrators",
    "expected_calibration_error",
]

_EPS = 1e-12


class LabCalibrator(ABC):
    """Fit-once, calibrate-one protocol for the comparison harness."""

    name: str = "lab_calibrator"

    @abstractmethod
    def fit(self, confidences: Sequence[float],
            correct: Sequence[int]) -> None:
        """Learn the map from raw confidence to calibrated probability."""

    @abstractmethod
    def calibrate(self, confidence: float) -> float:
        """Map one raw confidence to [0, 1]."""


def _check_fit_args(confidences: Sequence[float],
                    correct: Sequence[int]) -> tuple[list[float], list[int]]:
    confs = [float(c) for c in confidences]
    labels = [int(y) for y in correct]
    if len(confs) != len(labels):
        raise EvalError(
            f"confidences/correct length mismatch: {len(confs)} vs "
            f"{len(labels)}"
        )
    if len(confs) < 2:
        raise EvalError("calibrator fitting needs at least 2 samples")
    for c in confs:
        if not 0.0 <= c <= 1.0 or not math.isfinite(c):
            raise EvalError(f"confidence out of [0, 1]: {c!r}")
    for y in labels:
        if y not in (0, 1):
            raise EvalError(f"labels must be 0/1, got {y!r}")
    return confs, labels


def _clip(p: float) -> float:
    return min(1.0 - _EPS, max(_EPS, p))


def _logit(p: float) -> float:
    p = _clip(p)
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


class IdentityCalibrator(LabCalibrator):
    """The honest baseline: changes nothing."""

    name = "identity"

    def fit(self, confidences: Sequence[float],
            correct: Sequence[int]) -> None:
        _check_fit_args(confidences, correct)

    def calibrate(self, confidence: float) -> float:
        return _clip(float(confidence))


class TemperatureCalibrator(LabCalibrator):
    """Single-parameter scaling: ``sigmoid(logit(p) / T)``.

    ``T`` is fit by golden-section search on the negative
    log-likelihood in ``u = log T`` space (``T > 0`` always, so the
    ranking of scores is preserved — the same guarantee as the
    numpy implementation in :mod:`hugrgate.calibration.temperature`,
    reimplemented here in pure stdlib so the lab runs on the base
    install profile).
    """

    name = "temperature"

    def __init__(self) -> None:
        self.temperature = 1.0
        self._fitted = False

    def fit(self, confidences: Sequence[float],
            correct: Sequence[int]) -> None:
        confs, labels = _check_fit_args(confidences, correct)

        def nll(u: float) -> float:
            t = math.exp(u)
            total = 0.0
            for p, y in zip(confs, labels, strict=True):
                q = _clip(_sigmoid(_logit(p) / t))
                total -= y * math.log(q) + (1 - y) * math.log(1 - q)
            return total / len(confs)

        # Golden-section search on u in [-4, 4] (T in [e^-4, e^4]).
        gr = (math.sqrt(5.0) - 1.0) / 2.0
        lo, hi = -4.0, 4.0
        c = hi - gr * (hi - lo)
        d = lo + gr * (hi - lo)
        for _ in range(80):
            if nll(c) < nll(d):
                hi = d
            else:
                lo = c
            c = hi - gr * (hi - lo)
            d = lo + gr * (hi - lo)
        self.temperature = math.exp((lo + hi) / 2.0)
        self._fitted = True

    def calibrate(self, confidence: float) -> float:
        if not self._fitted:
            raise EvalError("TemperatureCalibrator used before fit")
        return _clip(_sigmoid(_logit(float(confidence))
                              / self.temperature))


class HistogramBinningCalibrator(LabCalibrator):
    """Non-parametric: map each confidence bin to its empirical accuracy."""

    name = "histogram_binning"

    def __init__(self, n_bins: int = 10) -> None:
        if n_bins < 2:
            raise EvalError(f"n_bins must be >= 2, got {n_bins}")
        self.n_bins = n_bins
        self._bin_acc: list[float] = []

    def fit(self, confidences: Sequence[float],
            correct: Sequence[int]) -> None:
        confs, labels = _check_fit_args(confidences, correct)
        sums = [0.0] * self.n_bins
        counts = [0] * self.n_bins
        for p, y in zip(confs, labels, strict=True):
            idx = min(int(p * self.n_bins), self.n_bins - 1)
            sums[idx] += y
            counts[idx] += 1
        overall = sum(labels) / len(labels)
        self._bin_acc = [
            (sums[i] / counts[i]) if counts[i] else overall
            for i in range(self.n_bins)
        ]

    def calibrate(self, confidence: float) -> float:
        if not self._bin_acc:
            raise EvalError("HistogramBinningCalibrator used before fit")
        idx = min(int(float(confidence) * self.n_bins), self.n_bins - 1)
        return _clip(self._bin_acc[idx])


class PackageCalibrator(LabCalibrator):
    """Adapter for :mod:`hugrgate.calibration` calibrators.

    Requires numpy (the ``ml`` extra) — exactly like the wrapped
    package.  Raises :class:`CalibrationError` when it is absent.
    """

    def __init__(self, calibrator: Any) -> None:
        self._inner = calibrator
        self.name = f"package:{getattr(calibrator, 'name', '?')}"

    def fit(self, confidences: Sequence[float],
            correct: Sequence[int]) -> None:
        confs, labels = _check_fit_args(confidences, correct)
        try:
            self._inner.fit(confs, labels)
        except Exception as exc:
            raise CalibrationError(
                f"package calibrator fit failed: {exc}"
            ) from exc

    def calibrate(self, confidence: float) -> float:
        try:
            return _clip(float(self._inner.calibrate(float(confidence))))
        except Exception as exc:
            raise CalibrationError(
                f"package calibrator failed: {exc}"
            ) from exc


def expected_calibration_error(
    correct: Sequence[int],
    confidences: Sequence[float],
    n_bins: int = 10,
) -> float:
    """ECE = sum_b |acc_b - conf_b| * (n_b / n), pure Python."""
    if len(correct) != len(confidences):
        raise EvalError("correct/confidences length mismatch")
    n = len(correct)
    if n == 0:
        raise EvalError("ECE needs at least one sample")
    if n_bins < 1:
        raise EvalError(f"n_bins must be >= 1, got {n_bins}")
    bin_acc = [0.0] * n_bins
    bin_conf = [0.0] * n_bins
    bin_n = [0] * n_bins
    for y, p in zip(correct, confidences, strict=True):
        idx = min(int(p * n_bins), n_bins - 1)
        bin_acc[idx] += y
        bin_conf[idx] += p
        bin_n[idx] += 1
    ece = 0.0
    for i in range(n_bins):
        if bin_n[i]:
            ece += abs(bin_acc[i] / bin_n[i] - bin_conf[i] / bin_n[i]) \
                * bin_n[i]
    return ece / n


def _nll(correct: Sequence[int], confidences: Sequence[float]) -> float:
    total = 0.0
    for y, p in zip(correct, confidences, strict=True):
        q = _clip(p)
        total -= y * math.log(q) + (1 - y) * math.log(1 - q)
    return total / len(correct)


@dataclass
class CalibrationComparison:
    """Per-method ECE/NLL on the eval split + ranking (slice 361)."""

    methods: dict[str, dict[str, float]]
    n_calib: int
    n_eval: int
    n_bins: int = 10

    @property
    def best(self) -> str | None:
        """Method with the lowest eval ECE."""
        if not self.methods:
            return None
        return min(self.methods, key=lambda m: self.methods[m]["ece"])

    @property
    def ranking(self) -> list[tuple[str, float]]:
        """(method, ece) sorted best-first."""
        return sorted(((m, d["ece"]) for m, d in self.methods.items()),
                      key=lambda kv: kv[1])

    def improvement_over_identity(self, method: str) -> float | None:
        """ECE reduction vs the identity baseline (None when absent)."""
        if method not in self.methods or "identity" not in self.methods:
            return None
        return (self.methods["identity"]["ece"]
                - self.methods[method]["ece"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "methods": {m: dict(d) for m, d in self.methods.items()},
            "n_calib": self.n_calib,
            "n_eval": self.n_eval,
            "n_bins": self.n_bins,
            "best": self.best,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CalibrationComparison:
        return cls(
            methods={m: dict(d) for m, d in data["methods"].items()},
            n_calib=data["n_calib"],
            n_eval=data["n_eval"],
            n_bins=data.get("n_bins", 10),
        )


def compare_calibrators(
    calib_confidences: Sequence[float],
    calib_correct: Sequence[int],
    eval_confidences: Sequence[float],
    eval_correct: Sequence[int],
    calibrators: Sequence[LabCalibrator],
    n_bins: int = 10,
) -> CalibrationComparison:
    """Fit each calibrator on the calib split; score on the eval split."""
    if not calibrators:
        raise EvalError("compare_calibrators needs at least one calibrator")
    eval_confs = [float(p) for p in eval_confidences]
    eval_y = [int(y) for y in eval_correct]
    if len(eval_confs) != len(eval_y):
        raise EvalError("eval confidences/correct length mismatch")
    if not eval_confs:
        raise EvalError("eval split is empty")
    methods: dict[str, dict[str, float]] = {}
    for cal in calibrators:
        cal.fit(calib_confidences, calib_correct)
        calibrated = [cal.calibrate(p) for p in eval_confs]
        methods[cal.name] = {
            "ece": expected_calibration_error(eval_y, calibrated, n_bins),
            "nll": _nll(eval_y, calibrated),
        }
    return CalibrationComparison(methods=methods, n_calib=len(calib_correct),
                                 n_eval=len(eval_y), n_bins=n_bins)


def _pairs_to_triples(
    pairs: Sequence[tuple[Any, DecisionResult | None]],
) -> tuple[list[float], list[int]]:
    """(expected, result) pairs -> (confidences, correct 0/1)."""
    confs: list[float] = []
    correct: list[int] = []
    for expected, result in pairs:
        if expected is None or result is None or result.value is None:
            continue
        if isinstance(expected, list):
            hit = set(result.value or []) == set(expected)
        else:
            hit = result.value == expected
        confs.append(float(result.probability))
        correct.append(1 if hit else 0)
    return confs, correct


def compare_backend_calibration(
    dataset: Mapping[str, Any],
    gate: HugrGate,
    backends: Sequence[str],
    calibrator_factories: Sequence[Callable[[], LabCalibrator]],
    *,
    calib_frac: float = 0.5,
    seed: int = 0,
    policy: DecisionPolicy | None = None,
    n_bins: int = 10,
    max_items: int | None = None,
) -> dict[str, CalibrationComparison]:
    """Per-backend calibrator comparison (slice 361).

    Each backend evaluates the dataset once; its scored pairs are
    split into calib/eval under ``seed``; every factory's calibrator
    is fit per backend on the calib split and scored on the eval
    split.  An identity baseline is always included.
    """
    if not backends:
        raise EvalError("need at least one backend")
    if not 0.0 < calib_frac < 1.0:
        raise EvalError(f"calib_frac must be in (0, 1), got {calib_frac}")
    if not calibrator_factories:
        raise EvalError("need at least one calibrator factory")
    policy = policy or DecisionPolicy()
    spec = DecisionSpec.from_dict(dataset["spec"])
    items = list(dataset.get("items", []))
    if max_items is not None:
        items = items[:max_items]
    if not items:
        raise EvalError("need at least one item")

    rng = random.Random(seed)
    results: dict[str, CalibrationComparison] = {}
    for backend in backends:
        pairs: list[tuple[Any, DecisionResult | None]] = []
        for item in items:
            try:
                result = gate.decide(dict(item["state"]), spec, policy,
                                     backend_name=backend)
            except Abstention:
                pairs.append((item.get("expected"), None))
            else:
                pairs.append((item.get("expected"), result))
        confs, correct = _pairs_to_triples(pairs)
        if len(confs) < 4:
            raise EvalError(
                f"backend {backend!r}: need 4+ scored items for a "
                f"calib/eval split, got {len(confs)}"
            )
        order = list(range(len(confs)))
        rng.shuffle(order)
        cut = max(2, round(len(order) * calib_frac))
        calib_idx, eval_idx = order[:cut], order[cut:]
        calibrators: list[LabCalibrator] = [IdentityCalibrator()]
        calibrators.extend(f() for f in calibrator_factories)
        results[backend] = compare_calibrators(
            [confs[i] for i in calib_idx],
            [correct[i] for i in calib_idx],
            [confs[i] for i in eval_idx],
            [correct[i] for i in eval_idx],
            calibrators,
            n_bins=n_bins,
        )
    return results
