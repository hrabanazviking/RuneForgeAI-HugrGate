"""Random forest backend. Slice 23.

Same train/predict/save/load contract as :class:`LogisticRegressionBackend`
(slice 22); additionally exposes per-feature importances in result metadata.
"""

from __future__ import annotations

from typing import Any

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency
    np = None  # type: ignore[assignment]
try:
    from sklearn.ensemble import RandomForestClassifier
except ImportError:  # pragma: no cover - optional dependency
    RandomForestClassifier = None

from hugrgate.backends.logreg import SklearnClassifierBackend
from hugrgate.errors import BackendError
from hugrgate.features import FeatureExtractor

__all__ = [
    "RandomForestBackend",
]


def _require_ml() -> None:
    """Deliberate error when the optional ML dependencies are absent."""
    if np is None or RandomForestClassifier is None:  # pragma: no cover
        raise BackendError(
            "the forest backend requires numpy and scikit-learn; install "
            "the 'ml' extra: pip install 'hugrgate[ml]'"
        )


class RandomForestBackend(SklearnClassifierBackend):
    """Bagged decision-tree ensemble backend."""

    name = "forest"

    def __init__(self,
                 model_name: str,
                 feature_pipeline: FeatureExtractor | None = None,
                 version: str = "1.0.0",
                 **classifier_kwargs: Any):
        kwargs = {"n_estimators": 200, "random_state": 42, "n_jobs": -1}
        kwargs.update(classifier_kwargs)
        super().__init__(model_name, feature_pipeline, version, **kwargs)

    def _make_classifier(self) -> RandomForestClassifier:
        _require_ml()
        return RandomForestClassifier(**self._classifier_kwargs)

    def _extra_metadata(self) -> dict[str, Any]:
        if not self.is_trained:
            return {}
        _require_ml()
        importances = np.asarray(self._clf.feature_importances_, dtype=float)
        names = self._pipeline.feature_names()
        return {
            "feature_importances": {
                name: float(imp)
                for name, imp in zip(names, importances, strict=True)
            },
        }

    def capabilities(self) -> dict[str, Any]:
        caps = super().capabilities()
        caps["algorithm"] = "random_forest"
        caps["ensemble"] = True
        caps["feature_importances"] = True
        return caps
