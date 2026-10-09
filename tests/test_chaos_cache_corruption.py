"""Slice 258 — cache corruption simulation tests."""

from __future__ import annotations

import pytest

from hugrgate.cache import DecisionCache
from hugrgate.chaos import CacheCorruptor
from hugrgate.errors import SpecError
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


@pytest.fixture
def cache():
    return DecisionCache(ttl_seconds=60.0, max_size=100)


@pytest.fixture
def seeded(cache):
    state = {"q": 1}
    policy = DecisionPolicy()
    result = DecisionResult(value="a", probability=0.9, backend="b1")
    assert cache.put(state, _spec(), policy, result) is True
    return cache, state, _spec(), policy


# --- detection ----------------------------------------------------------------------------

def test_corrupted_value_is_evicted_not_served(seeded):
    cache, state, spec, policy = seeded
    corruptor = CacheCorruptor(cache)
    assert corruptor.corrupt_value(state, spec, policy) is True
    assert cache.get(state, spec, policy) is None  # miss, not garbage
    stats = cache.stats()
    assert stats["corruptions"] == 1
    assert stats["misses"] == 1
    assert len(cache) == 0  # damaged entry evicted


def test_corrupted_metadata_is_detected(seeded):
    cache, state, spec, policy = seeded
    CacheCorruptor(cache).corrupt_metadata(state, spec, policy)
    assert cache.get(state, spec, policy) is None
    assert cache.stats()["corruptions"] == 1


def test_arbitrary_mutation_is_detected(seeded):
    cache, state, spec, policy = seeded
    CacheCorruptor(cache).tamper(
        state, spec, policy, lambda r: setattr(r, "probability", 0.12345))
    assert cache.get(state, spec, policy) is None
    assert cache.stats()["corruptions"] == 1


def test_corruptions_accumulate(seeded):
    cache, state, spec, policy = seeded
    corruptor = CacheCorruptor(cache)
    for value in ("x", "y"):
        cache.put(state, spec, policy,
                  DecisionResult(value="a", probability=0.9, backend="b1"))
        corruptor.corrupt_value(state, spec, policy, value=value)
        assert cache.get(state, spec, policy) is None
    assert cache.stats()["corruptions"] == 2


# --- recovery ---------------------------------------------------------------------------------

def test_cache_recovers_after_corruption(seeded):
    cache, state, spec, policy = seeded
    CacheCorruptor(cache).corrupt_value(state, spec, policy)
    assert cache.get(state, spec, policy) is None
    # Recompute and re-cache: service is restored.
    fresh = DecisionResult(value="b", probability=0.8, backend="b1")
    assert cache.put(state, spec, policy, fresh) is True
    assert cache.get(state, spec, policy).value == "b"
    assert cache.stats()["corruptions"] == 1  # lifetime counter kept


def test_tamper_on_miss_returns_false(cache):
    corruptor = CacheCorruptor(cache)
    assert corruptor.corrupt_value({"q": 9}, _spec(), DecisionPolicy()) is False
    assert cache.stats()["corruptions"] == 0


# --- no false positives --------------------------------------------------------------------------

def test_clean_traffic_never_trips_the_seal(cache):
    policy = DecisionPolicy()
    for i in range(100):
        state = {"q": i}
        cache.put(state, _spec(), policy,
                  DecisionResult(value="a", probability=0.9, backend="b1"))
    for i in range(100):
        assert cache.get({"q": i}, _spec(), policy).value == "a"
    assert cache.stats()["corruptions"] == 0
    assert cache.stats()["hits"] == 100


def test_checksum_survives_lru_touch_and_expiry_sweep(cache):
    policy = DecisionPolicy()
    cache.put({"q": 1}, _spec(), policy,
              DecisionResult(value="a", probability=0.9, backend="b1"))
    cache.put({"q": 2}, _spec(), policy,
              DecisionResult(value="b", probability=0.7, backend="b1"))
    assert cache.get({"q": 1}, _spec(), policy).value == "a"  # LRU touch
    assert len(cache) == 2  # expiry sweep
    assert cache.stats()["corruptions"] == 0


def test_corruptor_rejects_non_cache():
    with pytest.raises(SpecError, match="needs a DecisionCache"):
        CacheCorruptor("not-a-cache")  # type: ignore[arg-type]


def test_stats_contract():
    stats = DecisionCache().stats()
    assert stats["corruptions"] == 0
    assert set(stats) == {"size", "max_size", "ttl_seconds", "hits",
                          "misses", "corruptions", "hit_rate"}
