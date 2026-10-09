"""Privacy-event metrics. Slice 342.

Privacy enforcement (:mod:`hugrgate.privacy` and friends) *blocks*
things; this module *counts* the blocks — violations by taxonomy code
and privacy class, denied data flows, redaction events — without ever
recording what was blocked.  The metric labels are metadata-only by
construction:

- label *names* are drawn from a fixed allowlist; anything else
  raises;
- label *values* are length-capped and may never use a forbidden
  (payload) key name;
- the violating payload itself is never an argument to any function
  here — callers pass the already-raised exception.

Includes the slice's adversarial tests: attempts to smuggle payload
through label names or values are rejected, not recorded.
"""

from __future__ import annotations

from typing import Any

from hugrgate.errors import MetricError, PrivacyViolation
from hugrgate.observability.metrics import Counter, MetricRegistry
from hugrgate.observability.trace import FORBIDDEN_ATTRIBUTE_KEYS

__all__ = [
    "PrivacyEventMetrics",
]

#: The only label names privacy-event metrics accept.
_ALLOWED_LABELS = frozenset({"violation_code", "privacy_class", "backend"})

_MAX_VALUE_LEN = 256


def _scrub_labels(labels: dict[str, str]) -> dict[str, str]:
    scrubbed: dict[str, str] = {}
    for key, value in labels.items():
        if key not in _ALLOWED_LABELS:
            raise MetricError(
                f"privacy-event label {key!r} not in allowlist "
                f"{sorted(_ALLOWED_LABELS)}")
        if key in FORBIDDEN_ATTRIBUTE_KEYS:
            raise MetricError(
                f"privacy-event label {key!r} is a forbidden payload key")
        if not isinstance(value, str):
            raise MetricError(
                f"privacy-event label {key!r} value must be a string")
        if len(value) > _MAX_VALUE_LEN:
            raise MetricError(
                f"privacy-event label {key!r} value exceeds "
                f"{_MAX_VALUE_LEN} chars")
        scrubbed[key] = value
    return scrubbed


class PrivacyEventMetrics:
    """Count privacy enforcement events — metadata only, never payload."""

    def __init__(self, registry: MetricRegistry | None = None) -> None:
        self._registry = registry or MetricRegistry()
        self._violations: Counter = self._registry.counter(
            "hugrgate_privacy_violations_total",
            "Privacy violations by taxonomy code and class",
            labels=("violation_code", "privacy_class"))
        self._denied_flows: Counter = self._registry.counter(
            "hugrgate_privacy_denied_flows_total",
            "Denied data flows by backend",
            labels=("backend", "privacy_class"))
        self._redactions: Counter = self._registry.counter(
            "hugrgate_privacy_redactions_total",
            "Redaction events by backend",
            labels=("backend",))

    @property
    def registry(self) -> MetricRegistry:
        return self._registry

    def record_violation(self, error: PrivacyViolation,
                         privacy_class: str = "unknown") -> None:
        """Count one raised privacy violation (the exception, not data)."""
        if not isinstance(error, PrivacyViolation):
            raise MetricError(
                f"record_violation expects a PrivacyViolation, got "
                f"{type(error).__name__}")
        labels = _scrub_labels({
            "violation_code": error.code,
            "privacy_class": privacy_class,
        })
        self._violations.inc(1.0, labels=labels)

    def record_denied_flow(self, backend: str,
                           privacy_class: str = "unknown") -> None:
        """Count one denied data flow."""
        labels = _scrub_labels({"backend": backend or "unknown",
                                "privacy_class": privacy_class})
        self._denied_flows.inc(1.0, labels=labels)

    def record_redaction(self, backend: str) -> None:
        """Count one redaction event."""
        labels = _scrub_labels({"backend": backend or "unknown"})
        self._redactions.inc(1.0, labels=labels)

    def summary(self) -> dict[str, Any]:
        totals: dict[str, float] = {}
        by_code: dict[str, float] = {}
        for metric in self._registry.snapshot()["metrics"]:
            name = metric["name"]
            for row in metric["series"]:
                totals[name] = totals.get(name, 0.0) + row["value"]
                if name == "hugrgate_privacy_violations_total":
                    code = row["labels"]["violation_code"]
                    by_code[code] = by_code.get(code, 0.0) + row["value"]
        return {
            "totals": totals,
            "by_violation_code": by_code,
        }
