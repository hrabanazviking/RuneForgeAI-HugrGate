"""DecisionSpec — the decision contract. Slices 2-3."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
    options: Optional[List[str]] = None      # categorical
    statement: Optional[str] = None           # binary
    levels: Optional[List[str]] = None        # ordinal
    minimum: Optional[float] = None           # numeric
    maximum: Optional[float] = None           # numeric
    labels: Optional[List[str]] = None        # multilabel
    metadata: Dict[str, Any] = field(default_factory=dict)

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

    def value_space(self) -> List[str]:
        """All legal result values for this spec."""
        if self.type == "categorical":
            return list(self.options)
        if self.type == "binary":
            return ["true", "false"]
        if self.type == "ordinal":
            return list(self.levels)
        if self.type == "multilabel":
            return list(self.labels)
        return []  # numeric: continuous

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"type": self.type}
        for k in ("options", "statement", "levels", "minimum",
                  "maximum", "labels", "metadata"):
            v = getattr(self, k)
            if v is not None and v != {}:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DecisionSpec":
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
