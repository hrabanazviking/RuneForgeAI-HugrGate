"""Drift alerts. Slice 343.

Drift *detection* lives in :mod:`hugrgate.drift` (PSI over prediction
distributions) and :mod:`hugrgate.adaptive.drift_detect` (route drift);
this module is the *alerting* layer on top:

- :func:`alert_for_drift_report` turns a :class:`DriftReport` into an
  :class:`Alert` (``"watch"`` → warning, ``"action"`` → critical,
  ``"none"`` → no alert);
- :class:`AlertManager` evaluates rules with dedup keys and cooldowns:
  the same condition re-firing inside its cooldown is *suppressed and
  counted*, never re-emitted — alert storms are a failure mode, not a
  feature.

Alerts carry metadata only: names, severities, PSI values, sample
counts.  Never distributions, never payloads.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hugrgate.drift import DriftReport
from hugrgate.errors import AlertError

__all__ = [
    "SEVERITIES",
    "Alert",
    "AlertManager",
    "AlertRule",
    "alert_for_drift_report",
]

#: Allowed alert severities, ordered.
SEVERITIES = ("info", "warning", "critical")

_DRIFT_SEVERITY = {"none": None, "watch": "warning", "action": "critical"}


@dataclass(frozen=True)
class Alert:
    """One fired alert."""

    name: str
    severity: str
    dedup_key: str
    message: str
    fired_at: float = field(default_factory=time.time)
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise AlertError("alert name must be non-empty")
        if self.severity not in SEVERITIES:
            raise AlertError(
                f"unknown severity {self.severity!r}: expected one of "
                f"{list(SEVERITIES)}")
        if not self.dedup_key:
            raise AlertError("alert dedup_key must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "severity": self.severity,
            "dedup_key": self.dedup_key,
            "message": self.message,
            "fired_at": self.fired_at,
            "details": dict(self.details),
        }


def alert_for_drift_report(report: DriftReport,
                           monitor_name: str = "drift") -> Alert | None:
    """Translate a drift report into an alert (None when severity none).

    The PSI thresholds themselves belong to the detector; this function
    only maps the detector's verdict to alert semantics.
    """
    severity = _DRIFT_SEVERITY.get(report.severity)
    if severity is None:
        if report.severity not in _DRIFT_SEVERITY:
            raise AlertError(
                f"unknown drift severity: {report.severity!r}")
        return None
    return Alert(
        name=f"{monitor_name}.drift_{report.severity}",
        severity=severity,
        dedup_key=f"{monitor_name}:drift:{report.severity}",
        message=(f"drift {report.severity}: PSI={report.psi:.3f} "
                 f"(n_ref={report.n_reference}, n_live={report.n_live})"),
        details={
            "psi": round(report.psi, 4),
            "n_reference": report.n_reference,
            "n_live": report.n_live,
            "n_bins": report.n_bins,
        },
    )


@dataclass(frozen=True)
class AlertRule:
    """A named condition evaluated against a context dict."""

    name: str
    severity: str
    condition: Callable[[dict[str, Any]], bool]
    cooldown_s: float = 300.0
    dedup_key: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise AlertError("rule name must be non-empty")
        if self.severity not in SEVERITIES:
            raise AlertError(f"unknown severity {self.severity!r}")
        if not callable(self.condition):
            raise AlertError("rule condition must be callable")
        if self.cooldown_s < 0:
            raise AlertError("cooldown_s must be non-negative")

    def key(self) -> str:
        return self.dedup_key or self.name


class AlertManager:
    """Evaluate rules with dedup + cooldown; retain fired history."""

    def __init__(self, max_history: int = 500) -> None:
        if max_history < 1:
            raise AlertError("max_history must be positive")
        self._max_history = max_history
        self._lock = threading.Lock()
        self._rules: dict[str, AlertRule] = {}
        self._last_fired: dict[str, float] = {}
        self._suppressed: dict[str, int] = {}
        self._history: list[Alert] = []

    def add_rule(self, rule: AlertRule) -> None:
        with self._lock:
            if rule.name in self._rules:
                raise AlertError(f"duplicate rule name: {rule.name!r}")
            self._rules[rule.name] = rule

    def remove_rule(self, name: str) -> None:
        with self._lock:
            if name not in self._rules:
                raise AlertError(f"unknown rule: {name!r}")
            del self._rules[name]

    def evaluate(self, context: dict[str, Any]) -> list[Alert]:
        """Evaluate every rule; return newly fired alerts.

        Rule conditions must be pure predicates — an exception in a
        condition is wrapped in :class:`AlertError` and aborts the
        evaluation so a broken rule can never silently pass.
        """
        fired: list[Alert] = []
        now = time.time()
        with self._lock:
            rules = list(self._rules.values())
        for rule in rules:
            try:
                triggered = bool(rule.condition(dict(context)))
            except Exception as exc:
                raise AlertError(
                    f"rule {rule.name!r} condition raised: {exc}") from exc
            if not triggered:
                continue
            key = rule.key()
            with self._lock:
                last = self._last_fired.get(key, 0.0)
                if now - last < rule.cooldown_s:
                    self._suppressed[key] = self._suppressed.get(key, 0) + 1
                    continue
                self._last_fired[key] = now
                alert = Alert(
                    name=rule.name, severity=rule.severity, dedup_key=key,
                    message=f"rule {rule.name!r} triggered",
                    fired_at=now,
                    details={"context_keys": sorted(context.keys())})
                self._history.append(alert)
                del self._history[:max(0, len(self._history)
                                       - self._max_history)]
            fired.append(alert)
        return fired

    def suppressed_counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._suppressed)

    def history(self, limit: int = 50) -> list[Alert]:
        with self._lock:
            return list(self._history[-limit:])[::-1]

    def fire(self, alert: Alert, cooldown_s: float = 300.0) -> Alert | None:
        """Record a pre-built alert subject to dedup cooldown.

        Returns the alert when it fired, None when suppressed by
        cooldown (the suppression is counted).
        """
        if cooldown_s < 0:
            raise AlertError("cooldown_s must be non-negative")
        now = time.time()
        with self._lock:
            last = self._last_fired.get(alert.dedup_key, 0.0)
            if now - last < cooldown_s:
                self._suppressed[alert.dedup_key] = \
                    self._suppressed.get(alert.dedup_key, 0) + 1
                return None
            self._last_fired[alert.dedup_key] = now
            self._history.append(alert)
            del self._history[:max(0, len(self._history) - self._max_history)]
        return alert

    def evaluate_drift(self, report: DriftReport,
                       monitor_name: str = "drift") -> Alert | None:
        """Fire for a drift report, subject to the drift cooldown."""
        alert = alert_for_drift_report(report, monitor_name)
        if alert is None:
            return None
        return self.fire(alert)
