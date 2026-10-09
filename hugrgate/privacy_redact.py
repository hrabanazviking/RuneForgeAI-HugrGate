"""Redaction pipeline v2. Slice 232.

Slice 40's redaction was shallow: ``redact_state`` masked whole
values and ``redact_record`` dropped three top-level metadata keys.
Anything nested — a ``{"state": {...}}`` dict *inside* metadata, a
secret embedded in a longer string — sailed through.

This module is a composable redaction pipeline:

- :class:`Redactor` strategies: :class:`MaskRedactor`,
  :class:`PatternRedactor` (regexes over strings, including nested
  ones), :class:`HashRedactor` (deterministic salted hash, keeps
  joinability without reversibility), :class:`DropRedactor` (removes
  the field), :class:`TokenRedactor` (reversible via a token vault,
  slice 233).
- :class:`RedactionPipeline`: per-field redactors, per-
  :class:`Sensitivity` level strategies applied with
  :meth:`apply_with_labels`, and free-text scrubbing.
- :func:`redact_metadata`: deep scrub of provenance metadata —
  drops ``state``/``state_keys``/``raw_state`` keys at *any* depth
  and pattern-scrubs string values. :class:`PrivacyGuard.redact_record`
  now uses it (superset of the old behavior).
"""

from __future__ import annotations

import copy
import hashlib
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import replace as _replace_record
from typing import Any

from hugrgate.privacy_labels import FieldLabels, Sensitivity
from hugrgate.provenance import DecisionRecord

__all__ = [
    "DROP",
    "DropRedactor",
    "HashRedactor",
    "MaskRedactor",
    "PatternRedactor",
    "RedactionPipeline",
    "Redactor",
    "TokenRedactor",
    "redact_metadata",
]


class _Drop:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):  # pragma: no cover - trivial
        return "DROP"

    def __bool__(self):
        return False


#: Sentinel a redactor returns to remove the field entirely.
DROP = _Drop()

#: Metadata keys that must never survive redaction, at any depth.
STATE_METADATA_KEYS = frozenset({"state", "state_keys", "raw_state"})


class Redactor(ABC):
    """One redaction strategy."""

    name: str = "redactor"

    @abstractmethod
    def redact(self, value: Any, *, field: str,
               context: Mapping[str, Any] | None = None) -> Any:
        """Return the redacted value, or :data:`DROP` to remove it."""


class MaskRedactor(Redactor):
    """Replace the value with a fixed mask (optionally partial)."""

    name = "mask"

    def __init__(self, mask: str = "[REDACTED]", keep_last: int = 0):
        self.mask = mask
        self.keep_last = keep_last

    def redact(self, value: Any, *, field: str,
               context: Mapping[str, Any] | None = None) -> Any:
        if self.keep_last and isinstance(value, str) and \
                len(value) > self.keep_last:
            return f"{self.mask}…{value[-self.keep_last:]}"
        return self.mask


class PatternRedactor(Redactor):
    """Scrub regex matches inside strings (nested structures walked)."""

    name = "pattern"

    def __init__(self, patterns: list[tuple[str, str]] | None = None):
        self.patterns = [(name, re.compile(rx))
                         for name, rx in (patterns or [])]

    def redact(self, value: Any, *, field: str,
               context: Mapping[str, Any] | None = None) -> Any:
        return self.scrub(value)

    def scrub(self, value: Any) -> Any:
        """Apply all patterns to strings anywhere in ``value``."""
        if isinstance(value, str):
            for name, rx in self.patterns:
                value = rx.sub(f"[REDACTED:{name}]", value)
            return value
        if isinstance(value, Mapping):
            return {k: self.scrub(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            scrubbed = [self.scrub(v) for v in value]
            return type(value)(scrubbed) if isinstance(value, tuple) \
                else scrubbed
        return value


class HashRedactor(Redactor):
    """Deterministic salted hash — joinable, not reversible."""

    name = "hash"

    def __init__(self, salt: str = "hugrgate", digest_size: int = 16):
        if not salt:
            raise ValueError("salt must be non-empty")
        self.salt = salt
        self.digest_size = digest_size

    def redact(self, value: Any, *, field: str,
               context: Mapping[str, Any] | None = None) -> Any:
        digest = hashlib.sha256(
            f"{self.salt}:{field}:{value!r}".encode()).hexdigest()
        return f"hash:{digest[:self.digest_size]}"


class DropRedactor(Redactor):
    """Remove the field entirely."""

    name = "drop"

    def redact(self, value: Any, *, field: str,
               context: Mapping[str, Any] | None = None) -> Any:
        return DROP


class TokenRedactor(Redactor):
    """Reversible redaction via a token vault (slice 233).

    The vault needs ``tokenize(value) -> str``; any object with that
    method works (duck-typed to avoid a hard dependency direction).
    """

    name = "token"

    def __init__(self, vault: Any):
        if not hasattr(vault, "tokenize"):
            raise TypeError("vault must provide tokenize(value) -> str")
        self.vault = vault

    def redact(self, value: Any, *, field: str,
               context: Mapping[str, Any] | None = None) -> Any:
        return self.vault.tokenize(value)


class RedactionPipeline:
    """Ordered redaction strategies applied to state and text.

    Parameters
    ----------
    field_redactors:
        Exact field-name (or dotted path) -> redactor overrides.
    level_redactors:
        :class:`Sensitivity` -> redactor applied by
        :meth:`apply_with_labels` to fields at/above each level.
    text_redactor:
        :class:`PatternRedactor` applied to free text via
        :meth:`apply_to_text` and to string leaves during state
        redaction.
    """

    def __init__(self,
                 field_redactors: Mapping[str, Redactor] | None = None,
                 level_redactors: Mapping[Sensitivity, Redactor] | None = None,
                 text_redactor: PatternRedactor | None = None):
        self.field_redactors = dict(field_redactors or {})
        self.level_redactors = {Sensitivity(k): v
                                for k, v in (level_redactors or {}).items()}
        self.text_redactor = text_redactor

    def _redact_value(self, value: Any, field_path: str) -> Any:
        redactor = self.field_redactors.get(field_path)
        if redactor is None:
            if self.text_redactor is not None:
                return self.text_redactor.scrub(value)
            return value
        return redactor.redact(value, field=field_path)

    def apply_to_state(self, state: Mapping[str, Any]) -> \
            tuple[dict[str, Any], list[tuple[str, str]]]:
        """Redact per-field; returns ``(new_state, [(field, redactor)])``.

        Dotted paths are matched against ``field_redactors``; string
        leaves are additionally pattern-scrubbed when a text redactor
        is configured.
        """
        out = self._redact_mapping(state, "")

        def leaf_paths(node: Any, prefix: str) -> list[str]:
            paths: list[str] = []
            if isinstance(node, Mapping):
                for key, value in node.items():
                    path = f"{prefix}.{key}" if prefix else str(key)
                    if isinstance(value, Mapping):
                        paths.extend(leaf_paths(value, path))
                    else:
                        paths.append(path)
            return paths

        applied = [(path, self._redactor_name(path))
                   for path in leaf_paths(state, "")
                   if self._redactor_name(path) != "none"]
        return out, sorted(applied)

    def _redact_mapping(self, node: Mapping[str, Any],
                        prefix: str) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, Mapping):
                out[key] = self._redact_mapping(value, path)
            else:
                new_value = self._redact_value(value, path)
                if new_value is not DROP:
                    out[key] = new_value
        return out

    def _redactor_name(self, path: str) -> str:
        redactor = self.field_redactors.get(path)
        if redactor is not None:
            return redactor.name
        return "pattern" if self.text_redactor is not None else "none"

    def apply_with_labels(self, state: Mapping[str, Any],
                          labels: FieldLabels) -> \
            tuple[dict[str, Any], list[tuple[str, str]]]:
        """Redact every field at/above its level's strategy.

        For each labeled leaf, the strictest (highest) level with a
        configured redactor at or below the field's level wins.
        """
        labeled = labels.label_state(state)
        merged = dict(self.field_redactors)
        for path, level in labeled.items():
            if path in merged:
                continue
            eligible = [lvl for lvl in self.level_redactors
                        if lvl <= level]
            if eligible:
                merged[path] = self.level_redactors[max(eligible)]
        if not merged and self.text_redactor is None:
            return copy.deepcopy(dict(state)), []
        pipeline = RedactionPipeline(field_redactors=merged,
                                     text_redactor=self.text_redactor)
        return pipeline.apply_to_state(state)

    def apply_to_text(self, text: str) -> str:
        """Scrub free text with the pattern redactor (identity if none)."""
        if self.text_redactor is None:
            return text
        scrubbed = self.text_redactor.scrub(text)
        assert isinstance(scrubbed, str)
        return scrubbed


def redact_metadata(metadata: Mapping[str, Any],
                    text_redactor: PatternRedactor | None = None) -> \
        dict[str, Any]:
    """Deep-scrub provenance metadata.

    Drops ``state``/``state_keys``/``raw_state`` keys at any depth and
    pattern-scrubs remaining string values. Marks the result with
    ``redacted: True``. Idempotent.
    """
    def scrub(node: Any) -> Any:
        if isinstance(node, Mapping):
            out = {}
            for key, value in node.items():
                if key in STATE_METADATA_KEYS:
                    continue
                out[key] = scrub(value)
            return out
        if isinstance(node, list):
            return [scrub(v) for v in node]
        if isinstance(node, str) and text_redactor is not None:
            return text_redactor.scrub(node)
        return node

    result = scrub(dict(metadata))
    assert isinstance(result, dict)
    result["redacted"] = True
    return result


def redact_record_deep(record: DecisionRecord,
                       text_redactor: PatternRedactor | None = None) -> \
        DecisionRecord:
    """Return a copy of ``record`` with metadata deep-scrubbed."""
    return _replace_record(record, metadata=redact_metadata(
        record.metadata, text_redactor))
