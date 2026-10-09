"""Structured log schema for observability events. Slice 333.

:mod:`hugrgate.log` gives us JSON log *formatting* (slice 009); this
module gives us log *semantics*: a versioned schema for every
observability event the gate emits, so operators and log pipelines can
rely on field names instead of grepping free text.

- :data:`EVENT_SCHEMAS`: event name -> version + required/optional
  fields.  Schemas are append-only: new optional fields may be added,
  required fields are never removed or renamed (enforced by
  ``tests/test_observability_logschema.py``).
- :func:`validate_event` / :func:`emit_event`: validate-then-log; the
  payload denylist from :mod:`hugrgate.observability.trace` is enforced
  here too — a field named ``state`` or ``value`` raises instead of
  leaking a decision payload into the logs.
- :class:`ObservabilityFormatter`: extends
  :class:`hugrgate.log.JsonFormatter` with ``event``,
  ``event_version``, ``trace_id``, ``span_id``, and ``fields``.
- :class:`TraceLoggerAdapter`: stamps every record with the ambient
  trace/span ids.
"""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from typing import Any

from hugrgate.errors import ObservabilityError
from hugrgate.log import JsonFormatter, get_logger
from hugrgate.observability.trace import FORBIDDEN_ATTRIBUTE_KEYS

__all__ = [
    "EVENT_SCHEMAS",
    "ObservabilityFormatter",
    "TraceLoggerAdapter",
    "emit_event",
    "validate_event",
]

#: Versioned schemas for observability log events.  Append-only:
#: bumping a version may add optional fields but must never remove or
#: rename a required one.
EVENT_SCHEMAS: dict[str, dict[str, Any]] = {
    "decision.completed": {
        "version": 1,
        "required": ("spec_type", "backend", "verdict",
                     "probability_band", "latency_ms"),
        "optional": ("policy_privacy_class", "fallback_used",
                     "calibration_profile", "uncertainty"),
    },
    "decision.abstained": {
        "version": 1,
        "required": ("spec_type", "backend", "abstain_reason"),
        "optional": ("policy_privacy_class", "latency_ms"),
    },
    "backend.failed": {
        "version": 1,
        "required": ("backend", "error_code", "attempt"),
        "optional": ("latency_ms",),
    },
    "routing.chosen": {
        "version": 1,
        "required": ("chosen", "candidate_count", "policy_version"),
        "optional": ("propensity", "shadow", "privacy_class"),
    },
    "calibration.coverage_checked": {
        "version": 1,
        "required": ("method", "nominal_coverage", "n_samples",
                     "within_tolerance"),
        "optional": ("achieved_coverage", "ci_lower", "ci_upper"),
    },
    "privacy.blocked": {
        "version": 1,
        "required": ("violation_code", "privacy_class"),
        "optional": ("backend",),
    },
    "alert.fired": {
        "version": 1,
        "required": ("alert_name", "severity", "dedup_key"),
        "optional": ("details",),
    },
    "slo.breach": {
        "version": 1,
        "required": ("slo_name", "error_budget_remaining",
                     "burn_rate"),
        "optional": ("window_s",),
    },
    "drift.detected": {
        "version": 1,
        "required": ("monitor", "psi", "severity"),
        "optional": ("n_samples", "advisory"),
    },
}

_MAX_FIELD_LEN = 4096


def _scrub_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Reject payload/PII field names and over-long values."""
    scrubbed: dict[str, Any] = {}
    for key, value in fields.items():
        if not isinstance(key, str) or not key:
            raise ObservabilityError(
                f"log event field keys must be non-empty strings, got "
                f"{key!r}")
        if key in FORBIDDEN_ATTRIBUTE_KEYS:
            raise ObservabilityError(
                f"log event field {key!r} is forbidden: logs carry "
                f"metadata, never payload")
        if isinstance(value, str) and len(value) > _MAX_FIELD_LEN:
            raise ObservabilityError(
                f"log event field {key!r} exceeds {_MAX_FIELD_LEN} chars")
        scrubbed[key] = value
    return scrubbed


def validate_event(event: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Validate *fields* against the schema for *event*.

    Returns the scrubbed field dict.  Unknown events and missing
    required fields raise :class:`~hugrgate.errors.ObservabilityError`;
    unknown *optional* fields are kept (pipelines ignore what they do
    not know) but must still pass the payload scrub.
    """
    schema = EVENT_SCHEMAS.get(event)
    if schema is None:
        raise ObservabilityError(
            f"unknown observability log event: {event!r}")
    scrubbed = _scrub_fields(dict(fields))
    missing = [name for name in schema["required"] if name not in scrubbed]
    if missing:
        raise ObservabilityError(
            f"log event {event!r} missing required fields: {missing}")
    return scrubbed


def emit_event(logger_name: str, event: str, fields: dict[str, Any],
               level: int = logging.INFO,
               trace_id: str | None = None,
               span_id: str | None = None) -> None:
    """Validate and emit one structured observability log event."""
    scrubbed = validate_event(event, fields)
    logger = get_logger(logger_name)
    logger.log(level, event, extra={
        "obs_event": event,
        "obs_event_version": EVENT_SCHEMAS[event]["version"],
        "obs_fields": scrubbed,
        "obs_trace_id": trace_id,
        "obs_span_id": span_id,
    })


class ObservabilityFormatter(JsonFormatter):
    """JSON formatter that surfaces observability record extras.

    Records emitted via :func:`emit_event` gain ``event``,
    ``event_version``, ``fields``, ``trace_id``, and ``span_id`` keys;
    ordinary records format exactly like the base
    :class:`~hugrgate.log.JsonFormatter`.
    """

    def format(self, record: logging.LogRecord) -> str:
        import json
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        event = getattr(record, "obs_event", None)
        if event is not None:
            payload["event"] = event
            payload["event_version"] = getattr(record, "obs_event_version",
                                               1)
            payload["fields"] = getattr(record, "obs_fields", {})
        # Trace/span ids are surfaced whenever present, even on plain
        # (non-event) records — e.g. via TraceLoggerAdapter.
        trace_id = getattr(record, "obs_trace_id", None)
        span_id = getattr(record, "obs_span_id", None)
        if trace_id is not None:
            payload["trace_id"] = trace_id
        if span_id is not None:
            payload["span_id"] = span_id
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TraceLoggerAdapter(logging.LoggerAdapter):
    """Stamp every record with trace/span ids from the ambient span."""

    def __init__(self, logger: logging.Logger,
                 trace_id: str | None = None,
                 span_id: str | None = None) -> None:
        super().__init__(logger, {})
        self._trace_id = trace_id
        self._span_id = span_id

    def process(self, msg: Any, kwargs: MutableMapping[str, Any]
                ) -> tuple[Any, MutableMapping[str, Any]]:
        extra = dict(kwargs.get("extra") or {})
        if self._trace_id is not None:
            extra.setdefault("obs_trace_id", self._trace_id)
        if self._span_id is not None:
            extra.setdefault("obs_span_id", self._span_id)
        kwargs["extra"] = extra
        return msg, kwargs
