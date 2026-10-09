"""Slice 011 — state validation hardening.

``validate_state`` is the trust boundary between application data and
the runtime. It now rejects, loudly and specifically: non-mappings,
non-string keys (JSON would coerce them silently), non-finite floats
(not valid JSON), over-deep nesting, and oversized payloads.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.backends.rules import Rule, RuleBackend
from hugrgate.errors import SpecError
from hugrgate.validation import (
    DEFAULT_MAX_STATE_BYTES,
    DEFAULT_MAX_STATE_DEPTH,
    validate_state,
)


def _gate():
    gate = HugrGate()
    gate.register(RuleBackend(
        [Rule(condition=None, then="a", confidence=1.0)], name="r"))
    return gate


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def test_valid_states_pass():
    validate_state({})
    validate_state({"x": 1, "nested": {"list": [1, 2.5, "s", None, True]}})
    _gate().decide({"x": 1}, _spec(), DecisionPolicy())


def test_non_mapping_rejected():
    with pytest.raises(SpecError, match="must be a mapping"):
        validate_state("not a dict")
    with pytest.raises(SpecError, match="must be a mapping"):
        validate_state([("x", 1)])


def test_non_string_keys_rejected():
    with pytest.raises(SpecError, match="keys must be strings"):
        validate_state({1: "a"})
    with pytest.raises(SpecError, match="keys must be strings"):
        validate_state({"ok": {(2, 3): "tuple key"}})
    # int keys must not be silently coerced by json.dumps
    with pytest.raises(SpecError):
        _gate().decide({1: "a"}, _spec(), DecisionPolicy())


def test_non_finite_floats_rejected():
    with pytest.raises(SpecError, match="non-finite"):
        validate_state({"x": float("nan")})
    with pytest.raises(SpecError, match="non-finite"):
        validate_state({"x": [1.0, float("inf")]})
    with pytest.raises(SpecError, match="non-finite"):
        validate_state({"deep": {"deeper": float("-inf")}})


def test_unserializable_rejected():
    with pytest.raises(SpecError, match="not JSON-serializable"):
        validate_state({"x": object()})
    with pytest.raises(SpecError, match="not JSON-serializable"):
        validate_state({"x": {"y": object()}})


def test_depth_limit():
    deep = current = {}
    for _ in range(DEFAULT_MAX_STATE_DEPTH + 5):
        nxt = {}
        current["k"] = nxt
        current = nxt
    with pytest.raises(SpecError, match="max depth"):
        validate_state(deep)
    with pytest.raises(SpecError, match="max depth"):
        validate_state(deep, max_depth=4)
    # exactly at the limit passes
    shallow = current = {}
    for _ in range(DEFAULT_MAX_STATE_DEPTH - 1):
        nxt = {}
        current["k"] = nxt
        current = nxt
    validate_state(shallow)


def test_size_limit():
    big = {"blob": "x" * 5000}
    with pytest.raises(SpecError, match="exceeds"):
        validate_state(big, max_bytes=100)
    validate_state(big)  # default 1 MiB is generous
    assert DEFAULT_MAX_STATE_BYTES == 1_000_000


def test_custom_limits_are_respected():
    validate_state({"x": 1}, max_bytes=10**9, max_depth=1000)
    with pytest.raises(SpecError):
        validate_state({"x": 1}, max_bytes=1)


# --- failure / boundary --------------------------------------------------------

def test_decide_rejects_bad_state_with_spec_error():
    gate, spec = _gate(), _spec()
    with pytest.raises(SpecError):
        gate.decide({"x": float("nan")}, spec, DecisionPolicy())
    with pytest.raises(SpecError):
        gate.decide("nope", spec, DecisionPolicy())
