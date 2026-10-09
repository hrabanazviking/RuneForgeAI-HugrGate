"""Slice 121 — Ensemble caching.

Repeated states must not re-pay the full council. TTL + LRU, a
privacy bypass, member invalidation, and deep-copy isolation.
"""

from __future__ import annotations

import pytest

from hugrgate.ensemble import (
    CachedEnsemble,
    Ensemble,
    EnsembleCache,
)
from hugrgate.errors import PolicyError
from ensemble_fakes import CAT_SPEC, ConstantBackend

ALPHA = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}


def _cached(strategy="soft", **cache_kw):
    members = [ConstantBackend("a", "alpha", ALPHA),
               ConstantBackend("b", "alpha", ALPHA)]
    ens = Ensemble(members, strategy=strategy)
    return CachedEnsemble(ens, EnsembleCache(**cache_kw)), members


# --- success -----------------------------------------------------------------

def test_repeat_state_served_from_cache():
    cached, members = _cached()
    r1 = cached.evaluate({"x": 1}, CAT_SPEC())
    r2 = cached.evaluate({"x": 1}, CAT_SPEC())
    assert r1.value == r2.value == "alpha"
    assert all(m.calls == 1 for m in members)  # second was a hit
    assert cached.stats()["hits"] == 1
    assert cached.stats()["misses"] == 1


def test_different_state_is_a_miss():
    cached, members = _cached()
    cached.evaluate({"x": 1}, CAT_SPEC())
    cached.evaluate({"x": 2}, CAT_SPEC())
    assert all(m.calls == 2 for m in members)
    assert cached.stats()["misses"] == 2


def test_key_covers_strategy():
    members = [ConstantBackend("a", "alpha", ALPHA),
               ConstantBackend("b", "alpha", ALPHA)]
    cached = CachedEnsemble(Ensemble(members, strategy="soft"))
    cached.evaluate({"x": 1}, CAT_SPEC())
    # same members, new wrapper with a different strategy -> new key
    cached2 = CachedEnsemble(Ensemble(members, strategy="hard"),
                             cached.cache)
    cached2.evaluate({"x": 1}, CAT_SPEC())
    assert all(m.calls == 2 for m in members)


def test_ttl_zero_always_misses():
    cached, members = _cached(ttl_seconds=0.0)
    cached.evaluate({"x": 1}, CAT_SPEC())
    cached.evaluate({"x": 1}, CAT_SPEC())
    assert all(m.calls == 2 for m in members)
    assert cached.stats()["hits"] == 0


def test_lru_eviction():
    cached, members = _cached(maxsize=2)
    cached.evaluate({"x": 1}, CAT_SPEC())
    cached.evaluate({"x": 2}, CAT_SPEC())
    cached.evaluate({"x": 3}, CAT_SPEC())  # evicts x=1
    assert cached.stats()["evictions"] == 1
    cached.evaluate({"x": 1}, CAT_SPEC())  # miss again
    assert all(m.calls == 4 for m in members)


def test_invalidate_member_drops_its_entries():
    cached, members = _cached()
    cached.evaluate({"x": 1}, CAT_SPEC())
    assert cached.invalidate_member("a") == 1
    cached.evaluate({"x": 1}, CAT_SPEC())
    assert all(m.calls == 2 for m in members)
    assert cached.invalidate_member("zzz") == 0


def test_invalidate_clears_all():
    cached, _ = _cached()
    cached.evaluate({"x": 1}, CAT_SPEC())
    cached.evaluate({"x": 2}, CAT_SPEC())
    assert cached.invalidate() == 2
    assert len(cached.cache) == 0


def test_strict_privacy_bypasses_cache():
    cached, members = _cached()
    cached.evaluate({"x": 1}, CAT_SPEC(), privacy="strict")
    cached.evaluate({"x": 1}, CAT_SPEC(), privacy="strict")
    assert all(m.calls == 2 for m in members)  # never cached
    assert cached.stats()["misses"] == 0
    assert len(cached.cache) == 0


def test_deep_copy_isolation():
    cached, members = _cached()
    r1 = cached.evaluate({"x": 1}, CAT_SPEC())
    r1.metadata["ensemble"]["strategy"] = "MUTATED"
    r1.distribution["alpha"] = 999.0
    r2 = cached.evaluate({"x": 1}, CAT_SPEC())  # cache hit
    assert r2.metadata["ensemble"]["strategy"] == "soft"
    assert r2.distribution["alpha"] == pytest.approx(0.7)
    assert all(m.calls == 1 for m in members)


def test_wrapper_keeps_supplied_empty_cache():
    # regression: an empty EnsembleCache is falsy (len 0) and must not
    # be replaced by a default one
    members = [ConstantBackend("a", "alpha", ALPHA)]
    cache = EnsembleCache(maxsize=3, ttl_seconds=60.0)
    cached = CachedEnsemble(Ensemble(members, strategy="soft"), cache)
    assert cached.cache is cache
    assert cached.cache.maxsize == 3


def test_wrapper_exposes_ensemble_surface():
    cached, members = _cached(strategy="hard")
    assert cached.name == "ensemble[hard]"
    assert [m.name for m in cached.members] == ["a", "b"]


# --- failure -----------------------------------------------------------------

def test_validation():
    with pytest.raises(PolicyError, match="maxsize"):
        EnsembleCache(maxsize=0)
    with pytest.raises(PolicyError, match="ttl_seconds"):
        EnsembleCache(ttl_seconds=-1.0)
    with pytest.raises(PolicyError, match="privacy must be"):
        _cached()[0].evaluate({"x": 1}, CAT_SPEC(), privacy="paranoid")
    with pytest.raises(PolicyError, match="wraps an Ensemble"):
        CachedEnsemble(object())


# --- boundary -----------------------------------------------------------------

def test_maxsize_one_keeps_latest():
    cached, members = _cached(maxsize=1)
    cached.evaluate({"x": 1}, CAT_SPEC())
    cached.evaluate({"x": 1}, CAT_SPEC())
    assert cached.stats()["hits"] == 1
    cached.evaluate({"x": 2}, CAT_SPEC())  # evicts x=1
    cached.evaluate({"x": 1}, CAT_SPEC())  # miss, evicts x=2
    assert cached.stats()["evictions"] == 2
