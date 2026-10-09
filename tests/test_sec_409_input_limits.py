"""Slice 409 — input-size limits.

Named, tunable ingress policy over validation: key counts, key
lengths, batch amplification, and prompt text — the dimensions the
contract checks do not bound.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import HugrGateError, InputTooLarge, SpecError
from hugrgate.security.input_limits import (
    InputLimits,
    check_batch,
    check_prompt,
    check_state,
)


def test_small_state_passes():
    assert check_state({"x": 1, "y": "ok"}) > 0


def test_oversized_state_rejected_via_contract():
    # The byte dimension stays a contract error (backward compatible);
    # the policy configures the cap.
    limits = InputLimits(max_state_bytes=64)
    with pytest.raises(SpecError, match="exceeds 64 bytes"):
        check_state({"x": "y" * 1000}, limits)


def test_too_many_keys_rejected():
    limits = InputLimits(max_state_keys=4)
    with pytest.raises(InputTooLarge) as exc:
        check_state({f"k{i}": i for i in range(100)}, limits)
    assert exc.value.details["limit"] == "max_state_keys"


def test_giant_key_rejected():
    limits = InputLimits(max_key_length=16)
    with pytest.raises(InputTooLarge) as exc:
        check_state({"k" * 5000: 1}, limits)
    assert exc.value.details["limit"] == "max_key_length"


def test_deep_nesting_rejected_via_contract():
    limits = InputLimits(max_state_depth=8)
    nested: dict = {}
    cursor = nested
    for _ in range(50):
        cursor["n"] = {}
        cursor = cursor["n"]
    # Depth is a contract dimension: validate_state raises SpecError,
    # which check_state deliberately lets through (contract reuse).
    with pytest.raises(SpecError, match="depth"):
        check_state(nested, limits)


def test_contract_violations_still_spec_errors():
    with pytest.raises(SpecError):
        check_state({"x": float("inf")})  # non-finite: contract, not limit


def test_batch_size_cap():
    limits = InputLimits(max_batch_size=3)
    with pytest.raises(InputTooLarge) as exc:
        check_batch([{"x": 1}] * 10, limits)
    assert exc.value.details["limit"] == "max_batch_size"


def test_batch_byte_amplification_cap():
    limits = InputLimits(max_batch_bytes=200, max_state_bytes=10_000)
    with pytest.raises(InputTooLarge) as exc:
        check_batch([{"x": "y" * 100}] * 10, limits)
    assert exc.value.details["limit"] == "max_batch_bytes"


def test_batch_ok_returns_total():
    total = check_batch([{"x": 1}, {"y": 2}])
    assert total > 0


def test_prompt_limits():
    assert check_prompt("hello") == 5
    limits = InputLimits(max_prompt_chars=10)
    with pytest.raises(InputTooLarge) as exc:
        check_prompt("x" * 100, limits)
    assert exc.value.details["where"] == "prompt"
    with pytest.raises(InputTooLarge):
        check_prompt(123)  # type: ignore[arg-type]


def test_boundary_exactly_at_limit_passes():
    limits = InputLimits(max_state_keys=2)
    check_state({"a": 1, "b": 2}, limits)  # exactly 2: ok


def test_error_wire_round_trip():
    err = InputTooLarge("too big", limit="max_state_bytes")
    rebuilt = HugrGateError.from_dict(err.to_dict())
    assert isinstance(rebuilt, InputTooLarge)
