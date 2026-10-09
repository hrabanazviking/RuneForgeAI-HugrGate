"""Input feature contracts — what the model may assume.

Gjallarbrú slice 042.

``hugrgate/features.py`` extractors turn raw state into flat
``{name: float}`` dicts, but nothing contracts the *input* side: which
features must be present, their dtypes, valid ranges, or what happens
with missing/extra keys. :class:`FeatureContract` (kind
``"input-features"``) declares:

- :class:`FeatureSpec`: ``name``, ``dtype`` (``float`` | ``int`` |
  ``bool`` | ``category``), ``required``, numeric ``minimum``/``maximum``,
  ``categories`` for categoricals, and a ``default`` for optional fields;
- validation with aggregated violations (missing, mistyped,
  out-of-range, unknown category);
- :meth:`select`: project a raw mapping onto the declared feature order —
  filling defaults, dropping or rejecting extras per ``allow_extra`` —
  producing the clean, ordered feature dict a backend can consume.

(This is ``hugrgate.contracts.features``; the existing
``hugrgate.features`` extractor module is untouched.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Mapping, Optional, Tuple

from hugrgate.contracts.schema import (
    DecisionContract,
    register_kind,
)
from hugrgate.errors import ContractError

__all__ = [
    "FEATURE_DTYPES",
    "FeatureSpec",
    "FeatureContract",
]

#: Dtypes a feature may declare.
FEATURE_DTYPES = ("float", "int", "bool", "category")


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


@dataclass(frozen=True)
class FeatureSpec:
    """One declared input feature."""

    name: str
    dtype: str = "float"
    required: bool = True
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    categories: Tuple[str, ...] = ()
    default: Any = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ContractError("feature name must be a non-empty string",
                                code="bad_feature")
        if self.dtype not in FEATURE_DTYPES:
            raise ContractError(
                f"unknown feature dtype {self.dtype!r}; dtypes: "
                f"{list(FEATURE_DTYPES)}", code="bad_feature_dtype")
        if not isinstance(self.required, bool):
            raise ContractError("'required' must be a bool",
                                code="bad_feature")
        if self.dtype == "category":
            if not self.categories:
                raise ContractError(
                    f"categorical feature {self.name!r} needs categories",
                    code="bad_feature")
            if any(not isinstance(c, str) or not c for c in self.categories):
                raise ContractError("categories must be non-empty strings",
                                    code="bad_feature")
            if len(set(self.categories)) != len(self.categories):
                raise ContractError("categories must be unique",
                                    code="bad_feature")
            if self.minimum is not None or self.maximum is not None:
                raise ContractError(
                    "categorical features take no minimum/maximum",
                    code="bad_feature")
        else:
            if self.categories:
                raise ContractError(
                    f"non-categorical feature {self.name!r} takes no "
                    f"categories", code="bad_feature")
            for bound in ("minimum", "maximum"):
                v = getattr(self, bound)
                if v is not None and not _is_num(v):
                    raise ContractError(f"{bound} must be numeric",
                                        code="bad_feature")
            if (self.minimum is not None and self.maximum is not None
                    and not self.minimum <= self.maximum):
                raise ContractError("minimum must be <= maximum",
                                    code="bad_feature")
            if self.dtype == "bool" and (
                    self.minimum is not None or self.maximum is not None):
                raise ContractError("bool features take no minimum/maximum",
                                    code="bad_feature")
        if not self.required and self.default is not None:
            msg = self.check(self.default)
            if msg is not None:
                raise ContractError(
                    f"default for {self.name!r} is invalid: {msg}",
                    code="bad_feature_default")

    def check(self, value: Any) -> Optional[str]:
        """Violation message for one value, or None when it fits."""
        if self.dtype == "float":
            if not _is_num(value):
                return _mistype(self, value)
        elif self.dtype == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                return _mistype(self, value)
        elif self.dtype == "bool":
            if not isinstance(value, bool):
                return _mistype(self, value)
        elif self.dtype == "category":
            if value not in self.categories:
                return (f"feature {self.name!r}: {value!r} not in "
                        f"categories {list(self.categories)}")
        if self.dtype in ("float", "int") and _is_num(value):
            if self.minimum is not None and value < self.minimum:
                return (f"feature {self.name!r}: {value} < minimum "
                        f"{self.minimum}")
            if self.maximum is not None and value > self.maximum:
                return (f"feature {self.name!r}: {value} > maximum "
                        f"{self.maximum}")
        return None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"name": self.name, "dtype": self.dtype}
        if not self.required:
            d["required"] = False
        if self.minimum is not None:
            d["minimum"] = self.minimum
        if self.maximum is not None:
            d["maximum"] = self.maximum
        if self.categories:
            d["categories"] = list(self.categories)
        if self.default is not None:
            d["default"] = self.default
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "FeatureSpec":
        if not isinstance(d, Mapping):
            raise ContractError("feature spec must be a mapping",
                                code="bad_feature")
        try:
            return cls(name=d["name"], dtype=d.get("dtype", "float"),
                       required=d.get("required", True),
                       minimum=d.get("minimum"), maximum=d.get("maximum"),
                       categories=tuple(d.get("categories", ())),
                       default=d.get("default"))
        except KeyError as e:
            raise ContractError(f"feature spec missing key: {e}",
                                code="bad_feature") from None


def _mistype(spec: FeatureSpec, value: Any) -> str:
    return (f"feature {spec.name!r} must be {spec.dtype}, got "
            f"{type(value).__name__}")


@register_kind
@dataclass
class FeatureContract(DecisionContract):
    """The input features a model may assume (kind ``"input-features"``).

    The "decision value" is the raw feature mapping itself.
    """

    kind: ClassVar[str] = "input-features"

    features: List[Dict[str, Any]] = field(default_factory=list)
    allow_extra: bool = True
    _specs: Tuple[FeatureSpec, ...] = field(init=False, repr=False,
                                           compare=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.features, list) or not self.features:
            raise ContractError("feature contract needs ≥1 feature",
                                code="no_features")
        try:
            specs = tuple(FeatureSpec.from_dict(v) for v in self.features)
        except ContractError as e:
            raise ContractError(f"invalid feature spec: {e.message}",
                                code=e.details.get("code", "bad_feature"))
        names = [s.name for s in specs]
        if len(set(names)) != len(names):
            raise ContractError(f"duplicate feature names: {names}",
                                code="duplicate_features")
        if not isinstance(self.allow_extra, bool):
            raise ContractError("'allow_extra' must be a bool",
                                code="bad_feature_contract")
        self._specs = specs
        self.features = [s.to_dict() for s in specs]

    @property
    def specs(self) -> Tuple[FeatureSpec, ...]:
        """Declared feature specs in order."""
        return self._specs

    def feature_names(self) -> List[str]:
        """Declared feature names in order (the column order)."""
        return [s.name for s in self._specs]

    @property
    def required_names(self) -> Tuple[str, ...]:
        """Names of required features."""
        return tuple(s.name for s in self._specs if s.required)

    def violations(self, values: Any) -> List[str]:
        """Every problem with a raw feature mapping (possibly empty)."""
        if isinstance(values, str) or not isinstance(values, Mapping):
            return [f"features must be a mapping, got "
                    f"{type(values).__name__}"]
        problems: List[str] = []
        for spec in self._specs:
            if spec.name not in values:
                if spec.required:
                    problems.append(
                        f"missing required feature: {spec.name!r}")
                continue
            msg = spec.check(values[spec.name])
            if msg is not None:
                problems.append(msg)
        if not self.allow_extra:
            known = {s.name for s in self._specs}
            extra = [k for k in values if k not in known]
            if extra:
                problems.append(f"undeclared features: {extra}")
        return problems

    def validate_value(self, value: Any) -> None:
        problems = self.violations(value)
        if problems:
            raise ContractError(
                f"{len(problems)} feature violation(s):\n" +
                "\n".join(f"  - {p}" for p in problems),
                code="feature_violation", violations=problems)

    def select(self, values: Mapping[str, Any]) -> Dict[str, Any]:
        """Project a raw mapping onto the declared, ordered feature dict.

        Missing optional features are filled from their defaults (None
        when no default); extras are dropped when ``allow_extra`` else
        rejected. Raises on any violation.
        """
        self.validate_value(values)
        assert isinstance(values, Mapping)
        out: Dict[str, Any] = {}
        for spec in self._specs:
            if spec.name in values:
                out[spec.name] = values[spec.name]
            else:
                out[spec.name] = spec.default
        return out

    def _payload_dict(self) -> Dict[str, Any]:
        return {"features": [dict(v) for v in self.features],
                "allow_extra": self.allow_extra}

    @classmethod
    def _from_payload(cls, d: Mapping[str, Any],
                      common: Dict[str, Any]) -> "FeatureContract":
        raw = d.get("features")
        if not isinstance(raw, list):
            raise ContractError("input-features payload needs a 'features' "
                                "list", code="missing_features")
        allow_extra = d.get("allow_extra", True)
        if not isinstance(allow_extra, bool):
            raise ContractError("'allow_extra' must be a bool",
                                code="bad_feature_contract")
        return cls(features=raw, allow_extra=allow_extra, **common)

    def describe(self) -> str:
        req = len(self.required_names)
        return (f"input-features contract {self.name or self.contract_id!r}: "
                f"{len(self._specs)} feature(s), {req} required, "
                f"extra {'allowed' if self.allow_extra else 'rejected'}")
