"""DecisionSpec — the decision contract. Slices 2-3."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import SpecError

__all__ = [
    "SPEC_TYPES",
    "DecisionSpec",
]

SPEC_TYPES = ("categorical", "binary", "ordinal", "numeric", "multilabel")


@dataclass
class DecisionSpec:
    """A model-independent decision specification.

    The application declares WHAT decision it needs; HugrGate figures out
    HOW to make it. The result value is always within this spec's space.
    """
    type: str
    options: list[str] | None = None      # categorical
    statement: str | None = None           # binary
    levels: list[str] | None = None        # ordinal
    minimum: float | None = None           # numeric
    maximum: float | None = None           # numeric
    labels: list[str] | None = None        # multilabel
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.type not in SPEC_TYPES:
            raise SpecError(f"unknown spec type: {self.type!r}",
                            valid_types=list(SPEC_TYPES))
        validator = {
            "categorical": self._validate_categorical,
            "binary": self._validate_binary,
            "ordinal": self._validate_ordinal,
            "numeric": self._validate_numeric,
            "multilabel": self._validate_multilabel,
        }[self.type]
        validator()

    def _validate_categorical(self):
        if not self.options or len(self.options) < 2:
            raise SpecError("categorical spec needs ≥2 options")
        if len(set(self.options)) != len(self.options):
            raise SpecError("categorical options must be unique")
        if any(not isinstance(o, str) or not o for o in self.options):
            raise SpecError("categorical options must be non-empty strings")

    def _validate_binary(self):
        if not self.statement or not isinstance(self.statement, str):
            raise SpecError("binary spec needs a statement string")

    def _validate_ordinal(self):
        if not self.levels or len(self.levels) < 2:
            raise SpecError("ordinal spec needs ≥2 levels")
        if len(set(self.levels)) != len(self.levels):
            raise SpecError("ordinal levels must be unique")

    def _validate_numeric(self):
        if self.minimum is None or self.maximum is None:
            raise SpecError("numeric spec needs minimum and maximum")
        if self.minimum >= self.maximum:
            raise SpecError("numeric minimum must be < maximum")

    def _validate_multilabel(self):
        if not self.labels or len(self.labels) < 1:
            raise SpecError("multilabel spec needs ≥1 label")
        if len(set(self.labels)) != len(self.labels):
            raise SpecError("multilabel labels must be unique")

    def value_space(self) -> list[str]:
        """All legal result values for this spec."""
        # __post_init__ validation guarantees the relevant field is set
        # for each type; the asserts below make that visible to checkers.
        if self.type == "categorical":
            assert self.options is not None
            return list(self.options)
        if self.type == "binary":
            return ["true", "false"]
        if self.type == "ordinal":
            assert self.levels is not None
            return list(self.levels)
        if self.type == "multilabel":
            assert self.labels is not None
            return list(self.labels)
        return []  # numeric: continuous

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type}
        for k in ("options", "statement", "levels", "minimum",
                  "maximum", "labels", "metadata"):
            v = getattr(self, k)
            if v is not None and v != {}:
                d[k] = v
        return d

    #: Keys accepted by :meth:`from_dict`. Unknown keys are rejected
    #: loudly (slice 008): a misspelled key must never silently fall
    #: back to its default.
    _KEYS = frozenset({
        "type", "options", "statement", "levels",
        "minimum", "maximum", "labels", "metadata",
    })

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DecisionSpec:
        # Slice 422: non-dict input used to escape as TypeError and
        # mixed-type keys broke sorted() (both fuzz-found, T-16).
        if not isinstance(d, dict):
            raise SpecError(
                f"spec must be a dict, got {type(d).__name__}",
                code="spec_not_mapping")
        unknown = set(d) - cls._KEYS
        if unknown:
            raise SpecError(
                f"unknown spec key(s): {sorted(unknown, key=repr)}; "
                f"expected keys: {sorted(cls._KEYS)}")
        # Slice 422: a missing "type" used to escape as KeyError
        # (fuzz-found, T-16). Missing required keys are SpecErrors.
        if "type" not in d:
            raise SpecError("spec is missing required key 'type'",
                            code="spec_missing_type")
        return cls(
            type=d["type"],
            options=d.get("options"),
            statement=d.get("statement"),
            levels=d.get("levels"),
            minimum=d.get("minimum"),
            maximum=d.get("maximum"),
            labels=d.get("labels"),
            metadata=d.get("metadata", {}),
        )
