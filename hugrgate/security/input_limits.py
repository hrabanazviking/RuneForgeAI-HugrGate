"""Input-size limits. Slice 409.

:func:`hugrgate.validation.validate_state` already caps bytes and
depth generously; this module is the *security* layer on top of it
(threat T-04): a deliberate, named, tunable :class:`InputLimits`
policy that also covers key counts, key lengths, batch
amplification, and prompt text — the dimensions validation does
not bound.

Ordering at ingress: limits first (cheap rejection of hostile
payloads), then validation, then privacy. :func:`check_state` runs
:func:`validate_state` itself so the security path reuses the
contract checks instead of duplicating them; limit breaches raise
:class:`InputTooLarge` (taxonomy error), contract breaches raise
the usual :class:`SpecError`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import InputTooLarge
from hugrgate.validation import (
    DEFAULT_MAX_STATE_BYTES,
    DEFAULT_MAX_STATE_DEPTH,
    validate_state,
)

__all__ = [
    "InputLimits",
    "check_batch",
    "check_prompt",
    "check_state",
]

_DEFAULT_MAX_KEYS = 10_000
_DEFAULT_MAX_KEY_LENGTH = 1_024
_DEFAULT_MAX_BATCH = 1_024
_DEFAULT_MAX_PROMPT_CHARS = 100_000


@dataclass(frozen=True)
class InputLimits:
    """Named, tunable ingress size policy."""

    max_state_bytes: int = DEFAULT_MAX_STATE_BYTES
    max_state_depth: int = DEFAULT_MAX_STATE_DEPTH
    max_state_keys: int = _DEFAULT_MAX_KEYS
    max_key_length: int = _DEFAULT_MAX_KEY_LENGTH
    max_batch_size: int = _DEFAULT_MAX_BATCH
    max_batch_bytes: int = DEFAULT_MAX_STATE_BYTES * 4
    max_prompt_chars: int = _DEFAULT_MAX_PROMPT_CHARS

    def describe(self) -> dict[str, int]:
        return {
            "max_state_bytes": self.max_state_bytes,
            "max_state_depth": self.max_state_depth,
            "max_state_keys": self.max_state_keys,
            "max_key_length": self.max_key_length,
            "max_batch_size": self.max_batch_size,
            "max_batch_bytes": self.max_batch_bytes,
            "max_prompt_chars": self.max_prompt_chars,
        }


def _count_keys(obj: Any) -> int:
    if isinstance(obj, Mapping):
        return len(obj) + sum(_count_keys(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return sum(_count_keys(v) for v in obj)
    return 0


def _longest_key(obj: Any, path: str = "") -> tuple[str, int]:
    worst: tuple[str, int] = (path, 0)
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            if isinstance(key, str) and len(key) > worst[1]:
                worst = (f"{path}.{key}" if path else key, len(key))
            candidate = _longest_key(value,
                                     f"{path}.{key}" if path else str(key))
            if candidate[1] > worst[1]:
                worst = candidate
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            candidate = _longest_key(value, f"{path}[{index}]")
            if candidate[1] > worst[1]:
                worst = candidate
    return worst


def _fail(limit: str, actual: Any, allowed: Any,
          where: str = "state") -> None:
    raise InputTooLarge(
        f"{where} exceeds {limit}: {actual} > {allowed}",
        limit=limit, actual=actual, allowed=allowed, where=where)


def check_state(state: Mapping[str, Any],
                limits: InputLimits | None = None) -> int:
    """Enforce limits on one state mapping; returns serialized bytes.

    Runs :func:`validate_state` first (contract reuse), then the
    security limits. Raises :class:`InputTooLarge` on breach.
    """
    limits = limits or InputLimits()
    # Contract checks first: JSON-serializable, finite, string keys,
    # depth, and the byte cap itself (validate_state owns the byte
    # dimension; the policy configures it).
    validate_state(state, max_bytes=limits.max_state_bytes,
                   max_depth=limits.max_state_depth)
    keys = _count_keys(state)
    if keys > limits.max_state_keys:
        _fail("max_state_keys", keys, limits.max_state_keys)
    key_path, key_len = _longest_key(state)
    if key_len > limits.max_key_length:
        _fail("max_key_length", f"{key_len} at {key_path!r}",
              limits.max_key_length)
    payload = json.dumps(dict(state), sort_keys=True, allow_nan=False)
    return len(payload.encode("utf-8"))


def check_batch(states: Sequence[Mapping[str, Any]],
                limits: InputLimits | None = None) -> int:
    """Enforce batch-amplification limits; returns total bytes."""
    limits = limits or InputLimits()
    count = len(states)
    if count > limits.max_batch_size:
        _fail("max_batch_size", count, limits.max_batch_size,
              where="batch")
    total = 0
    for index, state in enumerate(states):
        total += check_state(state, limits)
        if total > limits.max_batch_bytes:
            _fail("max_batch_bytes", total, limits.max_batch_bytes,
                  where=f"batch[{index}]")
    return total


def check_prompt(prompt: str,
                 limits: InputLimits | None = None) -> int:
    """Enforce prompt-text limits; returns character count."""
    limits = limits or InputLimits()
    if not isinstance(prompt, str):
        raise InputTooLarge("prompt must be a string",
                            limit="prompt_type",
                            actual=type(prompt).__name__)
    size = len(prompt)
    if size > limits.max_prompt_chars:
        _fail("max_prompt_chars", size, limits.max_prompt_chars,
              where="prompt")
    return size
