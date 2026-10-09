"""Slice 333 — structured log schema: validation, scrub, formatting."""

from __future__ import annotations

import io
import json
import logging

import pytest

from hugrgate.errors import ObservabilityError
from hugrgate.log import get_logger
from hugrgate.observability import logschema
from hugrgate.observability.logschema import (
    EVENT_SCHEMAS,
    ObservabilityFormatter,
    TraceLoggerAdapter,
    emit_event,
    validate_event,
)


def _full_decision_fields() -> dict:
    return {
        "spec_type": "categorical", "backend": "stub", "verdict": "accept",
        "probability_band": "0.9-1.0", "latency_ms": 3.2,
    }


def test_validate_event_success():
    out = validate_event("decision.completed", _full_decision_fields())
    assert out["verdict"] == "accept"


def test_validate_event_rejects_unknown_event():
    with pytest.raises(ObservabilityError):
        validate_event("nope.not_real", {})


def test_validate_event_rejects_missing_required():
    with pytest.raises(ObservabilityError, match="missing required"):
        validate_event("decision.completed", {"spec_type": "categorical"})


def test_validate_event_rejects_payload_fields():
    with pytest.raises(ObservabilityError, match="forbidden"):
        validate_event("decision.completed",
                       {**_full_decision_fields(), "value": "secret-decision"})
    with pytest.raises(ObservabilityError, match="forbidden"):
        validate_event("decision.completed",
                       {**_full_decision_fields(), "state": {}})


def test_validate_event_rejects_oversize_and_bad_keys():
    with pytest.raises(ObservabilityError):
        validate_event("decision.completed",
                       {**_full_decision_fields(), "note": "x" * 5000})
    with pytest.raises(ObservabilityError):
        validate_event("decision.completed",
                       {**_full_decision_fields(), "": "empty-key"})


def test_schemas_are_append_only_documented():
    # Every schema carries a version and non-empty required fields.
    for name, schema in EVENT_SCHEMAS.items():
        assert schema["version"] >= 1, name
        assert len(schema["required"]) >= 1, name
        assert len(set(schema["required"])) == len(schema["required"]), name


def test_emit_event_writes_structured_json():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(ObservabilityFormatter())
    logger = get_logger("test_logschema_emit")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        emit_event("test_logschema_emit", "decision.completed",
                   _full_decision_fields(),
                   trace_id="a" * 32, span_id="b" * 16)
    finally:
        logger.removeHandler(handler)
    line = stream.getvalue().strip()
    payload = json.loads(line)
    assert payload["event"] == "decision.completed"
    assert payload["event_version"] == 1
    assert payload["fields"]["verdict"] == "accept"
    assert payload["trace_id"] == "a" * 32
    assert payload["span_id"] == "b" * 16
    assert payload["level"] == "INFO"


def test_formatter_plain_records_unchanged():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(ObservabilityFormatter())
    logger = get_logger("test_logschema_plain")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("just a message")
    finally:
        logger.removeHandler(handler)
    payload = json.loads(stream.getvalue().strip())
    assert payload["message"] == "just a message"
    assert "event" not in payload


def test_emit_event_validates_before_logging():
    with pytest.raises(ObservabilityError):
        emit_event("test_logschema_emit", "decision.completed", {})


def test_trace_logger_adapter_stamps_ids():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(ObservabilityFormatter())
    logger = get_logger("test_logschema_adapter")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        adapter = TraceLoggerAdapter(logger, trace_id="t" * 32,
                                     span_id="s" * 16)
        adapter.info("hello")
    finally:
        logger.removeHandler(handler)
    payload = json.loads(stream.getvalue().strip())
    assert payload["trace_id"] == "t" * 32
    assert payload["span_id"] == "s" * 16


def test_logschema_exports_stay_inside_contract():
    assert set(logschema.__all__) == {
        "EVENT_SCHEMAS", "ObservabilityFormatter", "TraceLoggerAdapter",
        "emit_event", "validate_event"}
