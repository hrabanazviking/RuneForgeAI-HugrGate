"""Slice 308 — Time-decay weighting: math, horizons, weighted aggregates."""

from __future__ import annotations

import math

import pytest

from hugrgate.memory import (
    DecisionHistory,
    decay_weight,
    decayed_mean,
    effective_count,
    half_life_for_horizon,
    retrieve,
)
from hugrgate.memory.similarity import featurize_query
from hugrgate.provenance import DecisionRecord


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8)
    base.update(kw)
    return DecisionRecord(**base)


def test_decay_weight_basics():
    assert decay_weight(0.0, 100.0) == 1.0
    assert decay_weight(100.0, 100.0) == pytest.approx(0.5)
    assert decay_weight(200.0, 100.0) == pytest.approx(0.25)
    # monotonic decreasing
    assert decay_weight(10.0, 100.0) > decay_weight(50.0, 100.0)
    # bounded in [0, 1]; astronomically old ages underflow to 0.0
    assert 0.0 <= decay_weight(1e9, 1.0) <= 1.0
    assert decay_weight(1e9, 1.0) == 0.0


def test_decay_weight_clamps_negative_age():
    # clock skew: a future-dated episode counts as fresh, never > 1
    assert decay_weight(-500.0, 100.0) == 1.0


def test_decay_weight_rejects_bad_half_life():
    for bad in (0.0, -5.0, math.inf, math.nan):
        with pytest.raises(ValueError):
            decay_weight(10.0, bad)


def test_half_life_for_horizon():
    half_life = half_life_for_horizon(30 * 86400, target_weight=0.01)
    assert decay_weight(30 * 86400, half_life) == pytest.approx(0.01)
    # default target is 0.01
    assert half_life_for_horizon(100.0) == pytest.approx(
        half_life_for_horizon(100.0, target_weight=0.01))
    with pytest.raises(ValueError):
        half_life_for_horizon(0.0)
    with pytest.raises(ValueError):
        half_life_for_horizon(100.0, target_weight=0.0)
    with pytest.raises(ValueError):
        half_life_for_horizon(100.0, target_weight=1.0)


def test_effective_count():
    assert effective_count([], 100.0) == 0.0
    assert effective_count([0.0, 0.0, 0.0], 100.0) == pytest.approx(3.0)
    # one fresh + one half-life-old episode = 1.5 effective episodes
    assert effective_count([0.0, 100.0], 100.0) == pytest.approx(1.5)
    with pytest.raises(ValueError):
        effective_count([1.0], 0.0)


def test_decayed_mean():
    # fresh values dominate
    mean = decayed_mean([1.0, 0.0], [0.0, 100.0], 100.0)
    assert mean == pytest.approx(2.0 / 3.0)
    # equal ages -> plain mean
    assert decayed_mean([1.0, 0.0], [50.0, 50.0], 100.0) == pytest.approx(0.5)
    with pytest.raises(ValueError):
        decayed_mean([], [], 100.0)
    with pytest.raises(ValueError):
        decayed_mean([1.0], [1.0, 2.0], 100.0)
    with pytest.raises(ValueError):
        # every weight underflows to 0.0 -> explicit error, not NaN
        decayed_mean([1.0, 2.0], [1e12, 1e12], 1.0)


def test_retrieval_uses_shared_decay():
    # regression: retrieve() still honors half-life after the refactor
    import time

    hist = DecisionHistory()
    old = hist.record(_record(probability=0.7))
    hist._by_id[old.episode_id].recorded_at -= 30 * 86400
    new = hist.record(_record(probability=0.7))
    query = featurize_query(spec={"type": "binary"}, probability=0.7)
    results = retrieve(hist, query, k=2, alpha=0.0, beta=1.0, gamma=0.0,
                       half_life_seconds=86400.0, now=time.time())
    assert results[0].episode.episode_id == new.episode_id
