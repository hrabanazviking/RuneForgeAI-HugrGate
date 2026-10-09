"""Validation layer — the application never receives an invalid value. Slice 7."""

from __future__ import annotations

import json
from typing import Any, Mapping

from hugrgate.errors import SpecError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec


def validate_state(state: Mapping[str, Any]) -> None:
    """State must be a JSON-serializable dict."""
    if not isinstance(state, Mapping):
        raise SpecError("state must be a mapping",
                        code="state_not_mapping")
    try:
        json.dumps(dict(state))
    except (TypeError, ValueError) as e:
        raise SpecError(f"state is not JSON-serializable: {e}",
                        code="state_not_serializable")


def validate_result(result: DecisionResult, spec: DecisionSpec) -> None:
    """Result value must be within the spec's decision space."""
    if result.value is None:
        return  # abstention is always legal
    space = spec.value_space()
    if spec.type == "numeric":
        if not isinstance(result.value, (int, float)):
            raise SpecError(f"numeric result must be a number, "
                            f"got {type(result.value).__name__}")
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
