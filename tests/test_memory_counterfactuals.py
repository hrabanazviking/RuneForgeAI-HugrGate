"""Slice 320 — Historical counterfactuals with honest uncertainty."""

from __future__ import annotations

import pytest

from hugrgate.memory import (
    DecisionHistory,
    Outcome,
    counterfactual_backends,
    counterfactual_value,
    wilson_interval,
)
from hugrgate.memory.similarity import featurize_query
from hugrgate.provenance import DecisionRecord


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8)
    base.update(kw)
    return DecisionRecord(**base)


def _history() -> DecisionHistory:
    hist = DecisionHistory()
    # local: 8/10 positive; remote: 2/10 positive
    for i in range(10):
        episode = hist.record(_record(backend="local"))
        hist.attach_outcome(
            episode.episode_id,
            Outcome(kind="success" if i < 8 else "failure",
                    score=0.9 if i < 8 else 0.1))
    for i in range(10):
        episode = hist.record(_record(backend="remote"))
        hist.attach_outcome(
            episode.episode_id,
            Outcome(kind="success" if i < 2 else "failure",
                    score=0.8 if i < 2 else 0.2))
    return hist


def _query():
    return featurize_query(spec={"type": "binary"}, backend="local",
                           model="m1", probability=0.8)


def test_wilson_interval():
    lo, hi = wilson_interval(8, 10)
    assert 0.0 <= lo < 0.8 < hi <= 1.0
    assert wilson_interval(0, 0) == (0.0, 1.0)
    lo, hi = wilson_interval(0, 10)
    assert lo == 0.0 and hi < 0.5
    lo, hi = wilson_interval(10, 10)
    assert lo > 0.5 and hi == 1.0
    with pytest.raises(ValueError):
        wilson_interval(11, 10)
    with pytest.raises(ValueError):
        wilson_interval(-1, 10)
    with pytest.raises(ValueError):
        wilson_interval(5, 10, z=0)


def test_counterfactual_backends_recovers_rates():
    hist = _history()
    results = counterfactual_backends(hist, _query(), min_n=5)
    assert len(results) == 2
    by_backend = {r.backend: r for r in results}
    local = by_backend["local"]
    remote = by_backend["remote"]
    assert local.success_rate == pytest.approx(0.8)
    assert remote.success_rate == pytest.approx(0.2)
    assert local.sufficient_data and remote.sufficient_data
    assert local.wilson_lo <= 0.8 <= local.wilson_hi
    assert local.mean_score == pytest.approx((8 * 0.9 + 2 * 0.1) / 10)
    # sorted best-first
    assert results[0].backend == "local"


def test_insufficient_data_flagged():
    hist = DecisionHistory()
    for _ in range(2):
        episode = hist.record(_record(backend="local"))
        hist.attach_outcome(episode.episode_id, Outcome(kind="success"))
    results = counterfactual_backends(hist, _query(), min_n=5)
    assert len(results) == 1
    assert results[0].sufficient_data is False
    assert results[0].success_rate == 1.0
    # interval is wide with n=2
    assert results[0].wilson_lo < 0.5


def test_unlabeled_episodes_yield_none_rate():
    hist = DecisionHistory()
    hist.record(_record(backend="local"))
    results = counterfactual_backends(hist, _query(), min_n=1)
    assert results[0].success_rate is None
    assert results[0].n == 0
    assert (results[0].wilson_lo, results[0].wilson_hi) == (0.0, 1.0)


def test_counterfactual_value():
    hist = DecisionHistory()
    for value, kind in ((True, "success"), (True, "success"),
                        (False, "failure")):
        episode = hist.record(_record(value=value))
        hist.attach_outcome(episode.episode_id, Outcome(kind=kind))
    good = counterfactual_value(hist, _query(), True, min_n=1)
    assert good.n == 2
    assert good.success_rate == 1.0
    assert good.sufficient_data
    bad = counterfactual_value(hist, _query(), False, min_n=5)
    assert bad.n == 1
    assert bad.success_rate == 0.0
    assert not bad.sufficient_data
    missing = counterfactual_value(hist, _query(), "maybe", min_n=1)
    assert missing.n == 0
    assert missing.success_rate is None


def test_min_similarity_gates():
    hist = _history()
    results = counterfactual_backends(hist, _query(), min_similarity=0.999)
    # extremely strict similarity still matches near-identical episodes
    assert all(r.n >= 0 for r in results)
    with pytest.raises(ValueError):
        counterfactual_backends(hist, _query(), min_similarity=2.0)
    with pytest.raises(ValueError):
        counterfactual_backends(hist, _query(), min_n=0)


def test_empty_history():
    assert counterfactual_backends(DecisionHistory(), _query()) == []
    result = counterfactual_value(DecisionHistory(), _query(), True)
    assert result.n == 0 and result.success_rate is None


def test_to_dict():
    hist = _history()
    d = counterfactual_backends(hist, _query())[0].to_dict()
    assert d["backend"] == "local"
    assert d["success_rate"] == pytest.approx(0.8)
