"""Feature preprocessing contract. Slice 21.

Raw decision ``state`` dicts are not model-ready.  This module defines the
:class:`FeatureExtractor` interface — ``extract(state) -> dict[str, float]``
— plus a small library of encoders and a composable :class:`Pipeline`.

All encoders are stateful in the same way: :meth:`fit` learns whatever the
encoder needs (category vocabularies, running means) from a sample of
states, then :meth:`extract` maps one state to a flat ``{name: float}``
feature dict.  :meth:`feature_names` always returns the column order used
by :meth:`transform_batch`, so backends can line vectors up with names.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import numpy as np

from hugrgate.errors import BackendError


class MissingValuePolicy(Enum):
    """How encoders treat absent / null fields."""

    ZERO = "zero"      # substitute 0.0
    MEAN = "mean"      # substitute the running mean seen during fit
    ERROR = "error"    # raise on any missing value


class FeatureExtractor(ABC):
    """Maps a raw state dict to a flat ``{feature_name: float}`` dict."""

    def __init__(self):
        self._fitted = False

    @property
    def fitted(self) -> bool:
        """True once :meth:`fit` has been called (or for stateless encoders)."""
        return self._fitted

    def fit(self, states: Iterable[Mapping[str, Any]]) -> "FeatureExtractor":
        """Learn encoder state from a sample of states. Default: no-op."""
        self._fitted = True
        return self

    @abstractmethod
    def extract(self, state: Mapping[str, Any]) -> Dict[str, float]:
        """Extract features from a single state."""

    @abstractmethod
    def feature_names(self) -> List[str]:
        """Column names, in the order used by :meth:`transform_batch`."""

    def transform_batch(self, states: Sequence[Mapping[str, Any]]) -> np.ndarray:
        """Encode many states into an ``(n_samples, n_features)`` array."""
        names = self.feature_names()
        rows = []
        for state in states:
            feats = self.extract(state)
            try:
                rows.append([float(feats[name]) for name in names])
            except KeyError as exc:
                raise BackendError(
                    f"extractor {type(self).__name__} did not emit "
                    f"feature {exc}; declared names: {names}")
        return np.asarray(rows, dtype=float)


def _coerce_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            raise ValueError(f"field {field!r} is NaN/inf")
        return float(value)
    raise ValueError(f"field {field!r} is not numeric: {value!r}")


class NumericEncoder(FeatureExtractor):
    """Pass numeric fields through as floats, with a missing-value policy.

    Non-numeric, non-missing values always raise; NaN/inf count as missing.
    """

    def __init__(self, fields: Sequence[str],
                 missing: MissingValuePolicy = MissingValuePolicy.ZERO):
        super().__init__()
        if not fields:
            raise ValueError("NumericEncoder needs at least one field")
        self.fields = list(fields)
        self.missing = missing
        self._means: Dict[str, float] = {f: 0.0 for f in self.fields}
        self._fitted = True  # stateless unless MEAN policy needs fit data

    def fit(self, states: Iterable[Mapping[str, Any]]) -> "NumericEncoder":
        if self.missing is MissingValuePolicy.MEAN:
            totals = {f: 0.0 for f in self.fields}
            counts = {f: 0 for f in self.fields}
            for state in states:
                for f in self.fields:
                    v = state.get(f)
                    if v is None:
                        continue
                    try:
                        totals[f] += _coerce_number(v, f)
                        counts[f] += 1
                    except ValueError:
                        continue
            for f in self.fields:
                self._means[f] = totals[f] / counts[f] if counts[f] else 0.0
        self._fitted = True
        return self

    def _handle_missing(self, field: str) -> float:
        if self.missing is MissingValuePolicy.ERROR:
            raise BackendError(f"missing value for numeric field {field!r}")
        if self.missing is MissingValuePolicy.MEAN:
            return self._means[field]
        return 0.0

    def extract(self, state: Mapping[str, Any]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for f in self.fields:
            v = state.get(f)
            if v is None:
                out[f] = self._handle_missing(f)
                continue
            try:
                out[f] = _coerce_number(v, f)
            except ValueError:
                out[f] = self._handle_missing(f)
        return out

    def feature_names(self) -> List[str]:
        return list(self.fields)


class CategoricalEncoder(FeatureExtractor):
    """One-hot encoder for a single categorical field.

    Categories are learned by :meth:`fit` (sorted unique values) or given
    explicitly.  Unknown categories at extract time emit an all-zero vector
    (``handle_unknown="ignore"``) or raise (``"error"``).
    """

    def __init__(self, field: str,
                 categories: Optional[Sequence[str]] = None,
                 handle_unknown: str = "ignore"):
        super().__init__()
        if handle_unknown not in ("ignore", "error"):
            raise ValueError("handle_unknown must be 'ignore' or 'error'")
        self.field = field
        self.handle_unknown = handle_unknown
        self._categories: List[str] = list(categories) if categories else []
        if categories:
            self._fitted = True

    @property
    def categories(self) -> List[str]:
        return list(self._categories)

    def fit(self, states: Iterable[Mapping[str, Any]]) -> "CategoricalEncoder":
        seen = set()
        for state in states:
            v = state.get(self.field)
            if v is not None:
                seen.add(str(v))
        self._categories = sorted(seen)
        self._fitted = True
        return self

    def _column(self, category: str) -> str:
        return f"{self.field}__{category}"

    def extract(self, state: Mapping[str, Any]) -> Dict[str, float]:
        if not self._fitted:
            raise BackendError(
                f"CategoricalEncoder({self.field!r}) used before fit")
        value = state.get(self.field)
        sval = None if value is None else str(value)
        if sval is not None and sval not in self._categories:
            if self.handle_unknown == "error":
                raise BackendError(
                    f"unknown category {sval!r} for field {self.field!r}")
            sval = None  # -> all-zero vector
        return {self._column(c): 1.0 if c == sval else 0.0
                for c in self._categories}

    def feature_names(self) -> List[str]:
        return [self._column(c) for c in self._categories]


class TextLengthEncoder(FeatureExtractor):
    """Cheap text shape features: character length and word count.

    Useful as a lightweight stand-in where full text featurization is
    overkill.  Missing/non-string values count as empty text.
    """

    def __init__(self, field: str, include_words: bool = True,
                 normalize: Optional[float] = None):
        super().__init__()
        self.field = field
        self.include_words = include_words
        self.normalize = normalize
        self._fitted = True

    def _text(self, state: Mapping[str, Any]) -> str:
        v = state.get(self.field)
        return v if isinstance(v, str) else ""

    def extract(self, state: Mapping[str, Any]) -> Dict[str, float]:
        text = self._text(state)
        length = float(len(text))
        out = {f"{self.field}__len": length}
        if self.include_words:
            out[f"{self.field}__words"] = float(len(text.split()))
        if self.normalize:
            out = {k: v / self.normalize for k, v in out.items()}
        return out

    def feature_names(self) -> List[str]:
        names = [f"{self.field}__len"]
        if self.include_words:
            names.append(f"{self.field}__words")
        return names


class Pipeline(FeatureExtractor):
    """Chains extractors; merges their feature dicts into one flat vector.

    Duplicate feature names across child extractors raise at fit time —
    silent column collisions would corrupt downstream models.
    """

    def __init__(self, extractors: Sequence[FeatureExtractor]):
        super().__init__()
        if not extractors:
            raise ValueError("Pipeline needs at least one extractor")
        self.extractors = list(extractors)

    def fit(self, states: Iterable[Mapping[str, Any]]) -> "Pipeline":
        states = list(states)
        for ext in self.extractors:
            ext.fit(states)
        names = self.feature_names()
        if len(set(names)) != len(names):
            dupes = sorted({n for n in names if names.count(n) > 1})
            raise BackendError(
                f"Pipeline has duplicate feature names: {dupes}")
        self._fitted = True
        return self

    def extract(self, state: Mapping[str, Any]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for ext in self.extractors:
            out.update(ext.extract(state))
        return out

    def feature_names(self) -> List[str]:
        names: List[str] = []
        for ext in self.extractors:
            names.extend(ext.feature_names())
        return names
