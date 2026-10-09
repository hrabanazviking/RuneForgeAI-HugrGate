"""Probability calibration package. Slices 26-29.

Calibrators map raw classifier scores to trustworthy probabilities:

- :mod:`hugrgate.calibration.platt` — Platt scaling (sigmoid fit, independent
  Newton implementation)
- :mod:`hugrgate.calibration.isotonic` — isotonic regression (independent
  PAV implementation)
- :mod:`hugrgate.calibration.temperature` — single-parameter temperature scaling
- :mod:`hugrgate.calibration.metrics` — Brier, log loss, ECE, MCE, reliability data
- :mod:`hugrgate.calibration.profiles` — versioned calibration profiles +
  :class:`CalibratedBackend` wrapper

All calibrators are binary one-vs-rest units: ``fit(scores, labels)`` learns
the map from a score in any real range to a calibrated probability in
``[0, 1]``.  Multiclass calibration applies one unit per class and
renormalizes (see :mod:`hugrgate.calibration.profiles`).
"""

from __future__ import annotations

# Base classes live in ._base so submodules can import them without
# creating a parent<->child import cycle with this __init__ (slice 002).
from hugrgate.calibration._base import Calibrator, CalibratorRegistry


# Submodule imports register their calibrator classes with the registry.
from hugrgate.calibration.platt import PlattCalibrator          # noqa: E402
from hugrgate.calibration.isotonic import IsotonicCalibrator    # noqa: E402
from hugrgate.calibration.temperature import (                 # noqa: E402
    TemperatureCalibrator,
)
from hugrgate.calibration.online import OnlineCalibrator       # noqa: E402
from hugrgate.calibration.window import SlidingWindowCalibrator  # noqa: E402
from hugrgate.calibration.bayes import BetaBinomialCalibrator   # noqa: E402
from . import (  # noqa: E402
    conformal, conformal_regression, group, metrics, perclass, pipeline,
    profiles,
)

CalibratorRegistry.register("platt", PlattCalibrator)
CalibratorRegistry.register("isotonic", IsotonicCalibrator)
CalibratorRegistry.register("temperature", TemperatureCalibrator)
CalibratorRegistry.register("online", OnlineCalibrator)
CalibratorRegistry.register("sliding-window", SlidingWindowCalibrator)
CalibratorRegistry.register("beta-binomial", BetaBinomialCalibrator)
CalibratorRegistry.register("constant-prior",
                             perclass._ConstantCalibrator)

__all__ = [
    "Calibrator",
    "CalibratorRegistry",
    "PlattCalibrator",
    "IsotonicCalibrator",
    "TemperatureCalibrator",
    "OnlineCalibrator",
    "SlidingWindowCalibrator",
    "BetaBinomialCalibrator",
    "conformal",
    "conformal_regression",
    "group",
    "metrics",
    "perclass",
    "pipeline",
    "profiles",
]
