"""Gradient boosting backend. Slice 24.

Same train/predict/save/load contract as :class:`LogisticRegressionBackend`
(slice 22), powered by scikit-learn's histogram-based gradient boosting
classifier.  Early stopping is configurable via constructor kwargs
(``early_stopping``, ``validation_fraction``, ``n_iter_no_change``).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sklearn.ensemble import HistGradientBoostingClassifier

from hugrgate.backends.logreg import SklearnClassifierBackend
from hugrgate.features import FeatureExtractor


class GradientBoostingBackend(SklearnClassifierBackend):
    """Histogram gradient-boosted trees backend."""

    name = "boosting"

    def __init__(self,
                 model_name: str,
                 feature_pipeline: Optional[FeatureExtractor] = None,
                 version: str = "1.0.0",
                 **classifier_kwargs: Any):
        kwargs = {
            "max_iter": 200,
            "learning_rate": 0.08,
            "random_state": 42,
            # Early stopping guards against overfitting on small data;
            # disable explicitly for tiny training sets.
            "early_stopping": True,
            "validation_fraction": 0.1,
            "n_iter_no_change": 10,
        }
        kwargs.update(classifier_kwargs)
        super().__init__(model_name, feature_pipeline, version, **kwargs)

    def _make_classifier(self) -> HistGradientBoostingClassifier:
        return HistGradientBoostingClassifier(**self._classifier_kwargs)

    def capabilities(self) -> Dict[str, Any]:
        caps = super().capabilities()
        caps["algorithm"] = "hist_gradient_boosting"
        caps["ensemble"] = True
        caps["early_stopping"] = bool(
            self._classifier_kwargs.get("early_stopping", True))
        return caps
