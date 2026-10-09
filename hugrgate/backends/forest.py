"""Random forest backend. Slice 23.

Same train/predict/save/load contract as :class:`LogisticRegressionBackend`
(slice 22); additionally exposes per-feature importances in result metadata.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
from sklearn.ensemble import RandomForestClassifier

from hugrgate.backends.logreg import SklearnClassifierBackend
from hugrgate.features import FeatureExtractor


class RandomForestBackend(SklearnClassifierBackend):
    """Bagged decision-tree ensemble backend."""

    name = "forest"

    def __init__(self,
                 model_name: str,
                 feature_pipeline: Optional[FeatureExtractor] = None,
                 version: str = "1.0.0",
                 **classifier_kwargs: Any):
        kwargs = {"n_estimators": 200, "random_state": 42, "n_jobs": -1}
        kwargs.update(classifier_kwargs)
        super().__init__(model_name, feature_pipeline, version, **kwargs)

    def _make_classifier(self) -> RandomForestClassifier:
        return RandomForestClassifier(**self._classifier_kwargs)

    def _extra_metadata(self) -> Dict[str, Any]:
        if not self.is_trained:
            return {}
        importances = np.asarray(self._clf.feature_importances_, dtype=float)
        names = self._pipeline.feature_names()
        return {
            "feature_importances": {
                name: float(imp)
                for name, imp in zip(names, importances)
            },
        }

    def capabilities(self) -> Dict[str, Any]:
        caps = super().capabilities()
        caps["algorithm"] = "random_forest"
        caps["ensemble"] = True
        caps["feature_importances"] = True
        return caps
