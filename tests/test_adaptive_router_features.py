"""Slice 129 — router feature extraction tests."""

from __future__ import annotations

import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.adaptive.router_features import (
    SPEC_TYPES,
    RouteContext,
    RouterFeatureExtractor,
)
from hugrgate.errors import BackendError


def make_ctx(**over):
    params = dict(
        state={"text": "hello world", "score": 0.7, "flag": True},
        spec=DecisionSpec(type="categorical", options=["a", "b"]),
        policy=DecisionPolicy(minimum_probability=0.6,
                              maximum_latency_ms=2000.0,
                              max_cost=5.0,
                              allowed_backends=["a", "b"],
                              preferred_backends=["a"]),
        candidates=["a", "b"],
        candidate_stats={"a": {"quality": 0.9, "latency_ms": 100.0,
                               "cost": 0.5},
                         "b": {"quality": 0.6, "latency_ms": 50.0,
                               "cost": 0.1}},
    )
    params.update(over)
    return RouteContext(**params)


# --- success ---------------------------------------------------------------

def test_feature_names_are_stable_and_complete():
    ext = RouterFeatureExtractor()
    names = ext.feature_names()
    assert len(names) == len(set(names)) == 23
    assert names == ext.feature_names()  # stable across calls
    assert ext.fitted  # stateless: fitted from birth

def test_spec_type_one_hot():
    ext = RouterFeatureExtractor()
    for t in SPEC_TYPES:
        kwargs = {"options": ["a", "b"]} if t == "categorical" else {}
        if t == "binary":
            kwargs = {"statement": "s?"}
        if t == "ordinal":
            kwargs = {"levels": ["l", "h"]}
        if t == "numeric":
            kwargs = {"minimum": 0.0, "maximum": 1.0}
        if t == "multilabel":
            kwargs = {"labels": ["x"]}
        ctx = make_ctx(spec=DecisionSpec(type=t, **kwargs))
        feats = ext.extract(ctx)
        for u in SPEC_TYPES:
            assert feats[f"spec_type__{u}"] == (1.0 if u == t else 0.0)

def test_policy_features_reflect_constraints():
    ext = RouterFeatureExtractor()
    feats = ext.extract(make_ctx())
    assert feats["policy__min_probability"] == 0.6
    assert feats["policy__max_latency_norm"] == pytest.approx(0.2)
    assert feats["policy__max_cost_norm"] == pytest.approx(0.05)
    assert feats["policy__remote_allowed"] == 0.0  # default policy: no remote
    assert feats["policy__strict_privacy"] == 0.0
    assert feats["policy__n_allowed"] == 2.0
    assert feats["policy__n_preferred"] == 1.0

def test_candidate_summary_features():
    ext = RouterFeatureExtractor()
    feats = ext.extract(make_ctx())
    assert feats["cand__n"] == 2.0
    assert feats["cand__best_quality"] == 0.9
    assert feats["cand__mean_quality"] == pytest.approx(0.75)
    assert feats["cand__quality_spread"] == pytest.approx(0.3)
    assert feats["cand__best_latency_norm"] == pytest.approx(0.005)
    assert feats["cand__best_cost_norm"] == pytest.approx(0.001)

def test_state_shape_features():
    ext = RouterFeatureExtractor()
    feats = ext.extract(make_ctx())
    assert feats["state__n_keys"] == 3.0
    assert feats["state__text_len"] == pytest.approx(0.011)  # "hello world"
    assert feats["state__numeric_frac"] == pytest.approx(1 / 3)

def test_extract_accepts_context_wrapped_in_mapping():
    ext = RouterFeatureExtractor()
    ctx = make_ctx()
    feats = ext.extract({"__route_context__": ctx})
    assert feats["cand__n"] == 2.0

def test_all_features_finite():
    import math
    ext = RouterFeatureExtractor()
    feats = ext.extract(make_ctx())
    assert all(math.isfinite(v) for v in feats.values())

def test_missing_context_degrades_to_zeros_not_nan():
    ext = RouterFeatureExtractor()
    ctx = make_ctx(policy=None, candidate_stats=None,
                   state={}, candidates=["a"])
    feats = ext.extract(ctx)
    assert feats["policy__min_probability"] == 0.0
    assert feats["cand__best_quality"] == 0.0
    assert feats["state__n_keys"] == 0.0
    assert feats["state__numeric_frac"] == 0.0

# --- failure ---------------------------------------------------------------

def test_non_context_mapping_rejected():
    ext = RouterFeatureExtractor()
    with pytest.raises(BackendError):
        ext.extract({"f": 1.0})

def test_pipeline_contract_transform_batch():
    import numpy as np
    ext = RouterFeatureExtractor()
    batch = ext.transform_batch([make_ctx(), make_ctx()])
    assert batch.shape == (2, 23)
