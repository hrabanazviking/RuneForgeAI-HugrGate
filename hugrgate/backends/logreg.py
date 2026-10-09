"""Logistic regression backend. Slice 22.

Trains on ``(state, label)`` pairs, emits ``predict_proba`` distributions,
and round-trips through pickle + :class:`ModelManifest`.  This module also
defines :class:`SklearnClassifierBackend`, the shared contract base reused
by the forest (slice 23) and boosting (slice 24) backends.
"""

from __future__ import annotations

import pickle
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency
    np = None  # type: ignore[assignment]
try:
    from sklearn.linear_model import LogisticRegression
except ImportError:  # pragma: no cover - optional dependency
    LogisticRegression = None

from hugrgate.backend import Backend
from hugrgate.errors import BackendError, BackendUnavailable
from hugrgate.features import FeatureExtractor, Pipeline
from hugrgate.models import ModelManifest, sha256_bytes
from hugrgate.result import DecisionResult
from hugrgate.security.serde_guards import restricted_loads

#: Slice 411: model files are untrusted bytes (threat T-01). The
#: manifest hash is an unsigned sidecar, so it cannot be the trust
#: root — unpickling goes through the allowlist instead. sklearn /
#: numpy / scipy module prefixes cover trained estimators;
#: hugrgate. covers our own pipeline/feature classes. Hostile
#: classes (os.system, builtins.eval, ...) fail closed.
_MODEL_UNPICKLE_MODULES = ("sklearn.", "numpy", "scipy.", "hugrgate.")
from hugrgate.spec import DecisionSpec


def _require_ml() -> None:
    """Deliberate error when the optional ML dependencies are absent."""
    if np is None or LogisticRegression is None:  # pragma: no cover
        raise BackendError(
            "scikit-learn backends require numpy and scikit-learn; install "
            "the 'ml' extra: pip install 'hugrgate[ml]'"
        )

__all__ = [
    "LogisticRegressionBackend",
    "SklearnClassifierBackend",
]

_SUPPORTED_TYPES = ("categorical", "binary")


class SklearnClassifierBackend(Backend):
    """Shared base for trainable scikit-learn classifier backends.

    Lifecycle: construct with a feature pipeline → :meth:`train` on
    ``(state, label)`` pairs → :meth:`evaluate` states against a spec.
    Subclasses only supply :meth:`_make_classifier` and optional
    :meth:`_extra_metadata`.
    """

    name = "sklearn_classifier"
    is_remote = False

    def __init__(self,
                 model_name: str,
                 feature_pipeline: FeatureExtractor | None = None,
                 version: str = "1.0.0",
                 **classifier_kwargs: Any):
        self._model_name = model_name
        self._model_version = version
        self._pipeline: FeatureExtractor = (
            feature_pipeline if feature_pipeline is not None else Pipeline([]))
        self._classifier_kwargs = classifier_kwargs
        self._clf: Any = None
        self._classes: list[str] = []
        self._trained_at: str = ""
        self._train_metrics: dict[str, float] = {}
        self._last_latency_ms: float = 0.0

    # -- subclass hooks -------------------------------------------------
    def _make_classifier(self) -> Any:
        raise NotImplementedError

    def _extra_metadata(self) -> dict[str, Any]:
        return {}

    # -- training --------------------------------------------------------
    @property
    def is_trained(self) -> bool:
        return self._clf is not None

    def _ensure_pipeline(self, states: Sequence[Mapping[str, Any]]) -> None:
        if isinstance(self._pipeline, Pipeline) and not self._pipeline.extractors:
            raise BackendError(
                f"{self.name}: no feature extractors configured; "
                "pass a feature_pipeline to train on raw states")
        if not self._pipeline.fitted:
            self._pipeline.fit(states)

    def train(self, pairs: Sequence[tuple[Mapping[str, Any], str]],
              sample_weight: Sequence[float] | None = None
              ) -> dict[str, float]:
        """Fit the classifier. Returns training metrics."""
        _require_ml()
        if len(pairs) < 2:
            raise BackendError(f"{self.name}: need ≥2 training pairs")
        states = [s for s, _ in pairs]
        labels = [str(label) for _, label in pairs]
        classes = sorted(set(labels))
        if len(classes) < 2:
            raise BackendError(
                f"{self.name}: need ≥2 distinct labels, got {classes}")

        self._ensure_pipeline(states)
        X = self._pipeline.transform_batch(states)
        y = np.asarray(labels)

        self._clf = self._make_classifier()
        fit_kwargs: dict[str, Any] = {}
        if sample_weight is not None:
            fit_kwargs["sample_weight"] = np.asarray(sample_weight, dtype=float)
        self._clf.fit(X, y)

        self._classes = [str(c) for c in self._clf.classes_]
        self._trained_at = datetime.now(timezone.utc).isoformat()
        train_pred = self._clf.predict(X)
        acc = float(np.mean(train_pred == y))
        self._train_metrics = {
            "train_accuracy": acc,
            "n_samples": float(len(pairs)),
            "n_features": float(X.shape[1]),
            "n_classes": float(len(self._classes)),
        }
        return dict(self._train_metrics)

    def _check_trained(self) -> None:
        if not self.is_trained:
            raise BackendUnavailable(
                f"{self.name}: model {self._model_name!r} is not trained yet")

    def predict_proba_dict(self, state: Mapping[str, Any]) -> dict[str, float]:
        """Raw class-probability dict for one state (no calibration)."""
        self._check_trained()
        X = self._pipeline.transform_batch([state])
        proba = self._clf.predict_proba(X)[0]
        return {cls: float(p) for cls, p in zip(self._classes, proba, strict=True)}

    # -- Backend contract -------------------------------------------------
    def capabilities(self) -> dict[str, Any]:
        return {
            "spec_types": list(_SUPPORTED_TYPES),
            "trainable": True,
            "predict_proba": True,
            "online_learning": False,
            "remote": self.is_remote,
            "model": self._model_name,
            "version": self._model_version,
            "trained": self.is_trained,
        }

    def supports(self, spec: DecisionSpec) -> bool:
        if spec.type not in _SUPPORTED_TYPES:
            return False
        if self.is_trained:
            return set(self._classes) == set(spec.value_space())
        return True

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Mapping[str, Any] | None = None
                 ) -> DecisionResult:
        if not self.supports(spec):
            raise BackendError(
                f"{self.name} cannot serve spec type {spec.type!r} "
                f"(classes={self._classes})")
        self._check_trained()
        started = time.perf_counter()
        raw = self.predict_proba_dict(state)
        # Deterministic key order: follow the spec's value space.
        distribution = {k: raw.get(k, 0.0) for k in spec.value_space()}
        total = sum(distribution.values())
        if total <= 0:
            n = len(distribution)
            distribution = {k: 1.0 / n for k in distribution}
        else:
            distribution = {k: v / total for k, v in distribution.items()}
        value = max(distribution, key=lambda k: distribution[k])
        probability = distribution[value]
        latency_ms = (time.perf_counter() - started) * 1000.0
        self._last_latency_ms = latency_ms
        metadata: dict[str, Any] = {
            "model": self._model_name,
            "model_version": self._model_version,
            "trained_at": self._trained_at,
            "features": self._pipeline.feature_names(),
            "train_metrics": dict(self._train_metrics),
        }
        metadata.update(self._extra_metadata())
        return DecisionResult(
            value=value,
            probability=probability,
            distribution=distribution,
            uncertainty=max(0.0, 1.0 - probability),
            backend=self.name,
            model=f"{self._model_name}@{self._model_version}",
            latency_ms=latency_ms,
            metadata=metadata,
        )

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.is_trained else "untrained",
            "backend": self.name,
            "model": self._model_name,
            "trained": self.is_trained,
            "last_latency_ms": self._last_latency_ms,
        }

    def estimated_latency(self) -> float:
        return self._last_latency_ms or 5.0

    def calibration_info(self) -> dict[str, Any]:
        return {"calibrated": False,
                "note": "attach a CalibrationProfile via "
                        "hugrgate.calibration.profiles.CalibratedBackend"}

    # -- persistence -------------------------------------------------------
    def manifest(self) -> ModelManifest:
        self._check_trained()
        return ModelManifest(
            name=self._model_name,
            version=self._model_version,
            backend=self.name,
            spec_type=",".join(_SUPPORTED_TYPES),
            features=self._pipeline.feature_names(),
            classes=list(self._classes),
            trained_at=self._trained_at,
            metrics=dict(self._train_metrics),
            extra={"classifier_kwargs": {
                k: v for k, v in self._classifier_kwargs.items()
                if isinstance(v, (str, int, float, bool)) or v is None}},
        )

    def _payload(self) -> bytes:
        return pickle.dumps({
            "classifier": self._clf,
            "pipeline": self._pipeline,
            "classes": self._classes,
            "trained_at": self._trained_at,
            "train_metrics": self._train_metrics,
            "classifier_kwargs": self._classifier_kwargs,
            "model_name": self._model_name,
            "model_version": self._model_version,
        })

    def save(self, path: str) -> str:
        """Persist model pickle + ``<path>.manifest.json``. Returns path."""
        self._check_trained()
        payload = self._payload()
        manifest = self.manifest()
        manifest.payload_hash = sha256_bytes(payload)
        with open(path, "wb") as fh:
            fh.write(payload)
        with open(path + ".manifest.json", "w") as fh:
            fh.write(manifest.to_json())
        return path

    @classmethod
    def load(cls, path: str) -> SklearnClassifierBackend:
        """Load a model saved with :meth:`save` (manifest verified)."""
        with open(path, "rb") as fh:
            payload = fh.read()
        with open(path + ".manifest.json") as fh:
            manifest = ModelManifest.from_json(fh.read())
        manifest.verify(payload)
        # Slice 411: restricted unpickle — the manifest is an unsigned
        # sidecar, so a rewritten manifest cannot bless a hostile
        # payload. Only sklearn/numpy/scipy classes may materialize.
        blob = restricted_loads(payload,
                                allowed_modules=_MODEL_UNPICKLE_MODULES)
        obj = cls.__new__(cls)
        SklearnClassifierBackend.__init__(
            obj,
            model_name=blob.get("model_name", manifest.name),
            feature_pipeline=blob["pipeline"],
            version=blob.get("model_version", manifest.version),
            **blob.get("classifier_kwargs", {}),
        )
        obj._clf = blob["classifier"]
        obj._classes = blob["classes"]
        obj._trained_at = blob["trained_at"]
        obj._train_metrics = blob["train_metrics"]
        return obj


class LogisticRegressionBackend(SklearnClassifierBackend):
    """Multinomial/one-vs-rest logistic regression backend."""

    name = "logreg"

    def _make_classifier(self) -> LogisticRegression:
        _require_ml()
        kwargs = {"max_iter": 1000}
        kwargs.update(self._classifier_kwargs)
        return LogisticRegression(**kwargs)

    def capabilities(self) -> dict[str, Any]:
        caps = super().capabilities()
        caps["algorithm"] = "logistic_regression"
        caps["linear"] = True
        return caps
