"""Validation layer — the application never receives an invalid value. Slice 7;
hardened in slice 011."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

from hugrgate.errors import SpecError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "validate_result",
    "validate_state",
]

#: Default cap on the serialized state size (1 MiB). Guards the cache-key
#: hash, the provenance store, and the HTTP wire against hostile payloads.
DEFAULT_MAX_STATE_BYTES = 1_000_000

#: Default cap on state nesting depth. Guards against RecursionError in
#: serialization and pathological cache-key costs.
DEFAULT_MAX_STATE_DEPTH = 64


def _check_keys(obj: Any, path: str = "state") -> None:
    """Reject non-string mapping keys (JSON would coerce them silently)."""
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            if not isinstance(key, str):
                raise SpecError(
                    f"{path}: state keys must be strings, "
                    f"got {type(key).__name__}",
                    code="state_key_not_string")
            _check_keys(value, f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            _check_keys(value, f"{path}[{index}]")


def _check_depth(obj: Any, max_depth: int) -> None:
    """Iterative depth check — no recursion, no RecursionError."""
    stack = [(obj, 1)]
    while stack:
        current, depth = stack.pop()
        if depth > max_depth:
            raise SpecError(
                f"state nesting exceeds max depth {max_depth}",
                code="state_too_deep")
        if isinstance(current, Mapping):
            stack.extend((v, depth + 1) for v in current.values())
        elif isinstance(current, (list, tuple)):
            stack.extend((v, depth + 1) for v in current)


def _check_finite(obj: Any, path: str = "state") -> None:
    """Reject NaN/Infinity: not valid JSON, not valid decision input."""
    stack = [(obj, path)]
    while stack:
        current, where = stack.pop()
        if isinstance(current, float) and not math.isfinite(current):
            raise SpecError(
                f"{where}: non-finite float {current!r} is not valid state",
                code="state_not_finite")
        elif isinstance(current, Mapping):
            stack.extend((v, f"{where}.{k}") for k, v in current.items())
        elif isinstance(current, (list, tuple)):
            stack.extend((v, f"{where}[{i}]")
                         for i, v in enumerate(current))


def validate_state(state: Mapping[str, Any],
                   max_bytes: int = DEFAULT_MAX_STATE_BYTES,
                   max_depth: int = DEFAULT_MAX_STATE_DEPTH) -> None:
    """State must be a JSON-serializable dict with string keys.

    Rejects non-mappings, non-string keys (JSON would coerce them
    silently), non-finite floats, over-deep nesting, and oversized
    payloads. Limits are generous by default and tunable per call.
    """
    if not isinstance(state, Mapping):
        raise SpecError("state must be a mapping",
                        code="state_not_mapping")
    _check_keys(state)
    _check_depth(state, max_depth)
    _check_finite(state)
    try:
        payload = json.dumps(dict(state), sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as e:
        raise SpecError(f"state is not JSON-serializable: {e}",
                        code="state_not_serializable") from e
    if len(payload.encode("utf-8")) > max_bytes:
        raise SpecError(
            f"state serialized size exceeds {max_bytes} bytes",
            code="state_too_large")


def validate_result(result: DecisionResult, spec: DecisionSpec) -> None:
    """Result value must be within the spec's decision space."""
    if result.value is None:
        return  # abstention is always legal
    space = spec.value_space()
    if spec.type == "numeric":
        if not isinstance(result.value, (int, float)):
            raise SpecError(f"numeric result must be a number, "
                            f"got {type(result.value).__name__}")
        # _validate_numeric guarantees both bounds are set.
        assert spec.minimum is not None and spec.maximum is not None
        if not (spec.minimum <= result.value <= spec.maximum):
            raise SpecError(f"numeric result {result.value} outside "
                            f"[{spec.minimum}, {spec.maximum}]")
        return
    if spec.type == "multilabel":
        if not isinstance(result.value, list):
            raise SpecError("multilabel result must be a list")
        bad = [v for v in result.value if v not in space]
        if bad:
            raise SpecError(f"multilabel values outside spec: {bad}")
        return
    if result.value not in space:
        raise SpecError(
            f"result value {result.value!r} not in spec space {space}")
    # Distribution keys must be within the value space
    if result.distribution:
        bad_keys = [k for k in result.distribution if k not in space]
        if bad_keys:
            raise SpecError(
                f"distribution keys outside spec: {bad_keys}")
