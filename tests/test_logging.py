"""Slice 009 — logging architecture.

The library is silent by default (NullHandler, no output), ``configure_logging``
is the explicit opt-in, and the privacy rule holds: no decision ``state``
content or result value ever appears in a log record.
"""

from __future__ import annotations

import io
import json
import logging

import pytest

from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.backends.rules import Rule, RuleBackend
from hugrgate.circuit import CircuitBreaker
from hugrgate.errors import BackendError
from hugrgate.log import JsonFormatter, configure_logging, get_logger


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture()
def capture():
    root = logging.getLogger("hugrgate")
    handler = _Capture()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)


def _messages(handler):
    return [r.getMessage() for r in handler.records]


def test_library_is_silent_by_default():
    root = logging.getLogger("hugrgate")
    # Only the NullHandler the library installs itself; nothing that emits.
    assert all(isinstance(h, logging.NullHandler) for h in root.handlers)
    assert root.level == logging.NOTSET


def test_get_logger_returns_package_children():
    assert get_logger("hugrgate.core").name == "hugrgate.core"
    assert get_logger("core").name == "hugrgate.core"


def test_configure_logging_is_idempotent():
    try:
        configure_logging("DEBUG")
        configure_logging("INFO")
        root = logging.getLogger("hugrgate")
        managed = [h for h in root.handlers
                   if getattr(h, "_hugrgate_managed", False)]
        assert len(managed) == 1
        assert root.level == logging.INFO
    finally:
        root = logging.getLogger("hugrgate")
        for h in [h for h in root.handlers
                  if getattr(h, "_hugrgate_managed", False)]:
            root.removeHandler(h)
        root.setLevel(logging.NOTSET)


def test_json_formatter_emits_parseable_objects():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = get_logger("slice009-test")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        logger.warning("hello %s", "world")
    finally:
        logger.removeHandler(handler)
    payload = json.loads(stream.getvalue().strip())
    assert payload["level"] == "WARNING"
    assert payload["logger"] == "hugrgate.slice009-test"
    assert payload["message"] == "hello world"
    assert "timestamp" in payload


def test_backend_failure_is_logged_without_state(capture):
    from hugrgate.backend import Backend

    class Failing(Backend):
        name = "failing-009"
        def evaluate(self, state, spec, context=None):
            raise BackendError("kaboom")
        def capabilities(self):
            return {}
        def supports(self, spec):
            return True

    gate = HugrGate()
    gate.register(Failing())
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    secret_state = {"ssn": "123-45-6789", "x": 1.0}
    with pytest.raises(BackendError):
        gate.decide(secret_state, spec, DecisionPolicy())
    messages = _messages(capture)
    assert any("failing-009" in m for m in messages), messages
    # Privacy rule: payload must never appear in log records.
    assert not any("123-45-6789" in m for m in messages), messages


def test_circuit_transitions_are_logged(capture):
    breaker = CircuitBreaker("cb-009", failure_threshold=2,
                             reset_timeout_s=60.0)
    breaker.record_failure()
    breaker.record_failure()  # opens
    messages = _messages(capture)
    assert any("cb-009" in m and "opened" in m for m in messages), messages


def test_fallback_engagement_is_logged(capture):
    from hugrgate.backend import Backend
    from hugrgate.fallback import FallbackChain

    class Failing(Backend):
        name = "fail-009"
        def evaluate(self, state, spec, context=None):
            raise BackendError("nope")
        def capabilities(self):
            return {}
        def supports(self, spec):
            return True

    ok = RuleBackend(
        [Rule(condition={"field": "x", "gt": 1.0}, then="a", confidence=0.9)],
        name="ok-009")
    chain = FallbackChain([Failing(), ok])
    gate = HugrGate()
    gate.register(chain)
    result = gate.decide({"x": 2.0},
                         DecisionSpec(type="categorical", options=["a", "b"]),
                         DecisionPolicy())
    assert result.value == "a"
    messages = _messages(capture)
    assert any("fail-009" in m for m in messages), messages


def test_privacy_block_logs_backend_name_not_state(capture):
    from hugrgate.privacy import PrivacyGuard

    class Remote:
        name = "remote-009"
        is_remote = True

    guard = PrivacyGuard(remote_inference="forbidden")
    with pytest.raises(Exception):
        guard.check_backend(Remote(), DecisionPolicy())
    messages = _messages(capture)
    assert any("remote-009" in m for m in messages), messages


# --- failure / boundary --------------------------------------------------------

def test_configure_logging_rejects_garbage_level():
    with pytest.raises(ValueError):
        configure_logging("NOISY")
