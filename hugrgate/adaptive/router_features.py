"""Router feature extraction. Slice 129.

The contextual bandit (slice 130) chooses arms from *context*, so the
quality of adaptive routing stands or falls on the features it sees.
:class:`RouterFeatureExtractor` turns a routing decision's raw context —
the :class:`~hugrgate.spec.DecisionSpec`, the state, the
:class:`~hugrgate.policy.DecisionPolicy`, and the candidate backends —
into a fixed, documented, numeric feature vector.

It implements the slice-21 :class:`~hugrgate.features.FeatureExtractor`
contract (``extract`` / ``feature_names`` / ``transform_batch`` via the
ABC), so it plugs into any tooling built for that interface. It is
stateless — the column set is fixed at construction — so it is fitted
from birth and safe to share across threads.

Feature groups:

- ``spec_type__*`` — one-hot over the five spec types;
- ``state__*`` — size/shape of the raw state (key count, text length);
- ``policy__*`` — the application's routing constraints, normalized;
- ``cand__*`` — candidate-set shape and the competence summary of the
  field (best/mean/spread of expected quality, latency, cost).

All features are finite floats; missing context degrades to zeros, never
NaN, because a NaN feature would silently poison the bandit's linear
model downstream.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

from hugrgate.errors import BackendError
from hugrgate.features import FeatureExtractor
from hugrgate.policy import DecisionPolicy
from hugrgate.spec import DecisionSpec

__all__ = [
    "SPEC_TYPES",
    "RouteContext",
    "RouterFeatureExtractor",
]

SPEC_TYPES = ("categorical", "binary", "ordinal", "numeric", "multilabel")


class RouteContext:
    """Everything the router knows before choosing a backend.

    ``candidate_stats`` maps backend name -> summary dict with optional
    keys ``quality`` (expected, in [0,1]), ``latency_ms`` and ``cost``.
    Values outside their sane ranges are clipped, not rejected — the
    extractor must never crash a live routing decision.
    """

    def __init__(self, state: Mapping[str, Any], spec: DecisionSpec,
                 policy: Optional[DecisionPolicy],
                 candidates: Sequence[str],
                 candidate_stats: Optional[Mapping[str, Mapping[str, float]]]
                 = None) -> None:
        self.state = dict(state)
        self.spec = spec
        self.policy = policy
        self.candidates = list(candidates)
        self.candidate_stats = (
            {k: dict(v) for k, v in candidate_stats.items()}
            if candidate_stats else {})


def _clip(value: float, lo: float, hi: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return min(max(value, lo), hi)


class RouterFeatureExtractor(FeatureExtractor):
    """Fixed-column router context features for the adaptive router."""

    def __init__(self) -> None:
        super().__init__()
        self._fitted = True  # stateless: no fit data needed

    def feature_names(self) -> List[str]:
        names: List[str] = []
        names.extend(f"spec_type__{t}" for t in SPEC_TYPES)
        names.extend([
            "state__n_keys",
            "state__text_len",
            "state__numeric_frac",
            "policy__min_probability",
            "policy__max_latency_norm",
            "policy__max_cost_norm",
            "policy__remote_allowed",
            "policy__strict_privacy",
            "policy__n_allowed",
            "policy__n_preferred",
            "cand__n",
            "cand__best_quality",
            "cand__mean_quality",
            "cand__quality_spread",
            "cand__best_latency_norm",
            "cand__mean_latency_norm",
            "cand__best_cost_norm",
            "cand__mean_cost_norm",
        ])
        return names

    def extract(self, state: Mapping[str, Any]) -> Dict[str, float]:
        """Extract from a mapping; see :meth:`extract_context`.

        ``state`` may be a :class:`RouteContext` (preferred) or a plain
        mapping with keys ``"__route_context__"`` holding one. Anything
        else raises :class:`~hugrgate.errors.BackendError`.
        """
        if isinstance(state, RouteContext):
            return self.extract_context(state)
        ctx = state.get("__route_context__") if isinstance(state, Mapping) \
            else None
        if isinstance(ctx, RouteContext):
            return self.extract_context(ctx)
        raise BackendError(
            "RouterFeatureExtractor needs a RouteContext; got "
            f"{type(state).__name__}")

    def extract_context(self, ctx: RouteContext) -> Dict[str, float]:
        feats: Dict[str, float] = {}
        for t in SPEC_TYPES:
            feats[f"spec_type__{t}"] = 1.0 if ctx.spec.type == t else 0.0

        raw = ctx.state
        n_keys = len(raw)
        text_len = sum(len(v) for v in raw.values()
                       if isinstance(v, str))
        n_numeric = sum(1 for v in raw.values()
                        if isinstance(v, (int, float))
                        and not isinstance(v, bool))
        feats["state__n_keys"] = float(n_keys)
        feats["state__text_len"] = _clip(float(text_len) / 1000.0, 0.0, 10.0)
        feats["state__numeric_frac"] = (n_numeric / n_keys) if n_keys else 0.0

        policy = ctx.policy
        feats["policy__min_probability"] = \
            _clip(policy.minimum_probability if policy else 0.0, 0.0, 1.0)
        max_lat = policy.maximum_latency_ms if policy else None
        feats["policy__max_latency_norm"] = \
            _clip((max_lat / 10_000.0) if max_lat else 1.0, 0.0, 1.0)
        max_cost = policy.max_cost if policy else None
        feats["policy__max_cost_norm"] = \
            _clip((max_cost / 100.0) if max_cost else 1.0, 0.0, 1.0)
        feats["policy__remote_allowed"] = \
            1.0 if (policy is None or policy.remote_inference) else 0.0
        feats["policy__strict_privacy"] = \
            1.0 if (policy is not None
                    and policy.privacy_class == "strict") else 0.0
        feats["policy__n_allowed"] = float(
            len(policy.allowed_backends) if policy and policy.allowed_backends
            else len(ctx.candidates))
        feats["policy__n_preferred"] = float(
            len(policy.preferred_backends)
            if policy and policy.preferred_backends else 0)

        n_cand = len(ctx.candidates)
        feats["cand__n"] = float(n_cand)
        qualities = [_clip(s.get("quality", 0.0), 0.0, 1.0)
                     for s in ctx.candidate_stats.values()]
        latencies = [_clip(s.get("latency_ms", 0.0) / 10_000.0, 0.0, 1.0)
                     for s in ctx.candidate_stats.values()]
        costs = [_clip(s.get("cost", 0.0) / 100.0, 0.0, 1.0)
                 for s in ctx.candidate_stats.values()]
        if qualities:
            feats["cand__best_quality"] = max(qualities)
            feats["cand__mean_quality"] = sum(qualities) / len(qualities)
            feats["cand__quality_spread"] = max(qualities) - min(qualities)
        else:
            feats["cand__best_quality"] = 0.0
            feats["cand__mean_quality"] = 0.0
            feats["cand__quality_spread"] = 0.0
        feats["cand__best_latency_norm"] = min(latencies) if latencies else 0.0
        feats["cand__mean_latency_norm"] = \
            (sum(latencies) / len(latencies)) if latencies else 0.0
        feats["cand__best_cost_norm"] = min(costs) if costs else 0.0
        feats["cand__mean_cost_norm"] = \
            (sum(costs) / len(costs)) if costs else 0.0

        names = self.feature_names()
        missing = [n for n in names if n not in feats]
        if missing:  # pragma: no cover - internal consistency guard
            raise BackendError(
                f"router extractor dropped columns: {missing}")
        return {n: feats[n] for n in names}
