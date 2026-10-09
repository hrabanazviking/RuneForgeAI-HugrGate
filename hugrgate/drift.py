"""Calibration drift detection — PSI over prediction distributions. Slice 48.

:class:`DriftMonitor` snapshots the predicted-class confidence distribution
at calibration time (``fit_reference``) and compares it against live
traffic (``observe``) using the Population Stability Index (PSI):

    PSI = sum_b (live%_b - ref%_b) * ln(live%_b / ref%_b)

Industry rule of thumb, encoded as defaults:

- PSI < 0.10 — no significant drift,
- 0.10 ≤ PSI < 0.25 — watch; investigate the shift,
- PSI ≥ 0.25 — significant drift; recalibration advised.

When drift trips the alert threshold, :func:`recalibration_advisory`
produces a concrete, actionable recommendation instead of a bare number.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "PSI_ALERT",
    "PSI_WATCH",
    "DriftMonitor",
    "DriftReport",
    "population_stability_index",
    "recalibration_advisory",
]

PSI_WATCH = 0.10
PSI_ALERT = 0.25
_EPS = 1e-6


def population_stability_index(reference: list[float],
                               live: list[float]) -> float:
    """PSI between two same-length probability-mass lists."""
    psi = 0.0
    for ref, lv in zip(reference, live, strict=True):
        ref = max(ref, _EPS)
        lv = max(lv, _EPS)
        psi += (lv - ref) * math.log(lv / ref)
    return psi


def _categorical_psi(ref_labels: list[Any],
                     live_labels: list[Any]) -> float:
    """PSI between two label-frequency distributions (eps-smoothed)."""
    labels = set(ref_labels) | set(live_labels)
    ref_total = max(len(ref_labels), 1)
    live_total = max(len(live_labels), 1)
    ref_counts = {label: ref_labels.count(label) for label in labels}
    live_counts = {label: live_labels.count(label) for label in labels}
    ref = [ref_counts[label] / ref_total for label in labels]
    live = [live_counts[label] / live_total for label in labels]
    return population_stability_index(ref, live)


def _histogram(values: list[float], n_bins: int) -> list[float]:
    counts = [0] * n_bins
    for v in values:
        v = min(max(v, 0.0), 1.0)
        idx = min(int(v * n_bins), n_bins - 1)
        counts[idx] += 1
    total = len(values)
    return [c / total for c in counts] if total else [0.0] * n_bins


@dataclass
class DriftReport:
    """Outcome of one drift observation window."""
    psi: float
    alert: bool
    severity: str  # "none" | "watch" | "action"
    n_reference: int
    n_live: int
    n_bins: int
    reference_hist: list[float] = field(default_factory=list)
    live_hist: list[float] = field(default_factory=list)
    observed_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "psi": self.psi,
            "alert": self.alert,
            "severity": self.severity,
            "n_reference": self.n_reference,
            "n_live": self.n_live,
            "n_bins": self.n_bins,
            "reference_hist": self.reference_hist,
            "live_hist": self.live_hist,
            "observed_at": self.observed_at,
        }


class DriftMonitor:
    """Track prediction-distribution drift against a calibration baseline.

    Usage:
        monitor = DriftMonitor(alert_threshold=0.25)
        monitor.fit_reference(calibration_confidences)
        report = monitor.observe(live_confidences)
        if report.alert:
            print(recalibration_advisory(report))
    """

    def __init__(self, n_bins: int = 10,
                 alert_threshold: float = PSI_ALERT,
                 watch_threshold: float = PSI_WATCH,
                 min_live_samples: int = 30) -> None:
        if n_bins < 2:
            raise ValueError("n_bins must be >= 2")
        if not 0.0 < watch_threshold <= alert_threshold:
            raise ValueError("need 0 < watch_threshold <= alert_threshold")
        self.n_bins = n_bins
        self.alert_threshold = alert_threshold
        self.watch_threshold = watch_threshold
        self.min_live_samples = min_live_samples
        self._reference_hist: list[float] | None = None
        self._n_reference = 0
        self._history: list[DriftReport] = []
        # Streaming mode: per-prediction (label, confidence) observations.
        self._stream: list[tuple] = []
        self._last_stream_psi: float = 0.0

    @property
    def has_reference(self) -> bool:
        return self._reference_hist is not None

    def fit_reference(self, confidences: list[float]) -> None:
        """Snapshot the calibration-time confidence distribution."""
        if not confidences:
            raise ValueError("reference confidences must be non-empty")
        self._reference_hist = _histogram(confidences, self.n_bins)
        self._n_reference = len(confidences)

    def observe(self, label_or_confidences: Any,
                confidence: float | None = None) -> DriftReport | None:
        """Record predictions, in either of two modes.

        - ``observe([0.9, 0.7, ...])`` — histogram mode: compare a live
          confidence window against the fitted reference; returns a
          :class:`DriftReport`.
        - ``observe("label", 0.9)`` — streaming mode: record one
          prediction; drift is assessed later via :meth:`check_drift`.
        """
        if confidence is not None:
            self._stream.append((label_or_confidences, confidence))
            return None
        if isinstance(label_or_confidences, str):
            raise ValueError(
                "streaming observe needs (label, confidence); "
                "histogram observe needs a list of confidences")
        return self._observe_window(list(label_or_confidences))

    def _observe_window(self, confidences: list[float]) -> DriftReport:
        """Compare a live window against the reference; return a report."""
        if not self.has_reference:
            raise ValueError("no reference fitted — call fit_reference first")
        live_hist = _histogram(confidences, self.n_bins)
        psi = population_stability_index(self._reference_hist, live_hist)  # type: ignore[arg-type]
        if len(confidences) < self.min_live_samples:
            severity, alert = "none", False
        elif psi >= self.alert_threshold:
            severity, alert = "action", True
        elif psi >= self.watch_threshold:
            severity, alert = "watch", False
        else:
            severity, alert = "none", False
        report = DriftReport(
            psi=psi, alert=alert, severity=severity,
            n_reference=self._n_reference, n_live=len(confidences),
            n_bins=self.n_bins,
            reference_hist=list(self._reference_hist),  # type: ignore[arg-type]
            live_hist=live_hist)
        self._history.append(report)
        return report

    # -- streaming API ----------------------------------------------------
    def check_drift(self) -> bool:
        """Stream-mode drift check: PSI over label frequencies.

        Splits the streamed observations into an early half (reference)
        and a late half (live) and computes the categorical PSI between
        their label distributions. Returns True when PSI reaches the
        alert threshold. Needs at least 10 streamed observations.
        """
        n = len(self._stream)
        if n < 10:
            self._last_stream_psi = 0.0
            return False
        half = n // 2
        ref_labels = [label for label, _ in self._stream[:half]]
        live_labels = [label for label, _ in self._stream[half:]]
        self._last_stream_psi = _categorical_psi(ref_labels, live_labels)
        return self._last_stream_psi >= self.alert_threshold

    def psi(self) -> float:
        """PSI from the most recent :meth:`check_drift` (0.0 if never run)."""
        return self._last_stream_psi

    def stream_count(self) -> int:
        return len(self._stream)

    def history(self) -> list[DriftReport]:
        return list(self._history)


def recalibration_advisory(report: DriftReport) -> dict[str, Any]:
    """Turn a drift report into an actionable recalibration recommendation."""
    if report.severity == "none":
        return {"action": "none",
                "message": "Prediction distribution stable; "
                           "no recalibration needed.",
                "psi": report.psi}
    if report.severity == "watch":
        return {
            "action": "watch",
            "message": (
                f"PSI {report.psi:.3f} in the watch band "
                f"[{PSI_WATCH}, {PSI_ALERT}). Keep observing; check for "
                "upstream data changes before touching calibration."),
            "psi": report.psi,
            "recommended_steps": [
                "Extend the observation window to confirm the shift.",
                "Inspect per-bin histograms for the drifting region.",
                "Check upstream feature/pipeline changes.",
            ],
        }
    return {
        "action": "recalibrate",
        "message": (
            f"PSI {report.psi:.3f} >= alert threshold {PSI_ALERT}. "
            "Live prediction distribution has drifted significantly from "
            "calibration time — probabilities should no longer be trusted "
            "at face value."),
        "psi": report.psi,
        "recommended_steps": [
            "Collect fresh labeled data from the live distribution.",
            "Refit the calibrator on the new data (new profile version).",
            "Back-test the new profile on a holdout before promoting.",
            "Keep the old profile archived for rollback.",
            "Tighten policy minimum_probability until recalibrated.",
        ],
    }
