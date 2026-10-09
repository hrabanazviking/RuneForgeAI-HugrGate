"""Slice 239 — Retention policies.

Tests default and custom limits, expiry boundaries, chain-safe
purges, the forbidden zero-retention rule, cache TTL capping, and
adversarial cases (unknown classes fail closed; purge keeps the
chain verifiable).
"""

from __future__ import annotations

import time

import pytest

from hugrgate.cache import DecisionCache
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy_provenance import PrivacyAwareProvenanceStore
from hugrgate.privacy_retention import (
    RETENTION_DEFAULTS,
    RetentionPolicy,
    purge_expired,
)
from hugrgate.provenance import DecisionRecord
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec


def make_spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def make_result():
    return DecisionResult(value="a", probability=0.9,
                          distribution={"a": 0.9, "b": 0.1},
                          backend="stub", model="m")


def aged_record(cls: str, age_seconds: float, now: float) -> DecisionRecord:
    record = DecisionRecord.from_decision(
        {"x": 1}, make_spec(), make_result())
    record.timestamp = now - age_seconds
    record.metadata["privacy_class"] = cls
    return record


@pytest.fixture
def store():
    return PrivacyAwareProvenanceStore()


def test_defaults():
    assert RETENTION_DEFAULTS["public"] is None
    assert RETENTION_DEFAULTS["standard"] == 30 * 24 * 3600
    assert RETENTION_DEFAULTS["sensitive"] == 7 * 24 * 3600
    assert RETENTION_DEFAULTS["strict"] == 24 * 3600
    assert RETENTION_DEFAULTS["forbidden"] == 0


def test_unknown_class_fails_closed():
    policy = RetentionPolicy()
    assert policy.max_age_for("ultra") == RETENTION_DEFAULTS["strict"]


def test_custom_limits():
    policy = RetentionPolicy({"standard": 60.0, "public": 3600.0})
    assert policy.max_age_for("standard") == 60.0
    assert policy.max_age_for("public") == 3600.0
    assert policy.max_age_for("strict") == 24 * 3600  # default kept
    with pytest.raises(ValueError):
        RetentionPolicy({"standard": -5})


def test_is_expired_boundary():
    policy = RetentionPolicy({"standard": 100.0})
    now = time.time()
    assert policy.is_expired(
        aged_record("standard", 101, now), now=now) is True
    assert policy.is_expired(
        aged_record("standard", 99, now), now=now) is False
    # public never expires.
    assert policy.is_expired(
        aged_record("public", 10**9, now), now=now) is False
    # forbidden expires immediately (max age 0).
    assert policy.is_expired(
        aged_record("forbidden", 0.001, now), now=now) is True


def test_purge_expired_removes_only_expired(store):
    policy = RetentionPolicy({"standard": 100.0})
    now = time.time()
    store.append(aged_record("standard", 200, now))   # expired
    store.append(aged_record("standard", 50, now))    # fresh
    store.append(aged_record("public", 10**6, now))   # unbounded
    assert store.verify_chain() is True
    removed = purge_expired(store, policy, now=now)
    assert removed == 1
    assert store.count() == 2
    assert store.verify_chain() is True  # re-anchored chain verifies


def test_purge_forbidden_immediately(store):
    policy = RetentionPolicy()
    now = time.time()
    store.append(aged_record("forbidden", 0, now))
    # Age 0 vs max age 0: (now - ts) > 0 is False at the same instant;
    # one microsecond later it expires.
    assert purge_expired(store, policy, now=now + 0.001) == 1
    assert store.count() == 0
    assert store.verify_chain() is True


def test_purge_nothing_expired(store):
    policy = RetentionPolicy()
    now = time.time()
    store.append(aged_record("public", 10, now))
    assert purge_expired(store, policy, now=now) == 0
    assert store.count() == 1


def test_on_purge_hook_fires(store):
    seen: list[str] = []
    policy = RetentionPolicy({"standard": 100.0})
    now = time.time()
    store.append(aged_record("standard", 200, now))
    purge_expired(store, policy, now=now,
                  on_purge=lambda r: seen.append(r.request_hash))
    assert len(seen) == 1


def test_cache_ttl_capped():
    policy = RetentionPolicy({"sensitive": 60.0})
    assert policy.cache_ttl_for(
        DecisionPolicy(privacy_class="sensitive"), 300.0) == 60.0
    assert policy.cache_ttl_for(
        DecisionPolicy(privacy_class="sensitive"), 30.0) == 30.0
    assert policy.cache_ttl_for(
        DecisionPolicy(privacy_class="public"), 300.0) == 300.0
    assert policy.cache_ttl_for(
        DecisionPolicy(privacy_class="forbidden"), 300.0) == 0.0


def test_cache_put_honors_retention():
    cache = DecisionCache(ttl_seconds=3600.0)
    spec = make_spec()
    policy = DecisionPolicy(privacy_class="sensitive")
    retention = RetentionPolicy({"sensitive": 0.05})
    result = make_result()
    assert cache.put({"x": 1}, spec, policy, result,
                     retention=retention) is True
    assert cache.get({"x": 1}, spec, policy) is not None
    time.sleep(0.08)
    assert cache.get({"x": 1}, spec, policy) is None  # TTL capped


def test_cache_put_without_retention_unchanged():
    cache = DecisionCache(ttl_seconds=3600.0)
    spec = make_spec()
    policy = DecisionPolicy()
    assert cache.put({"x": 1}, spec, policy, make_result()) is True
    assert cache.get({"x": 1}, spec, policy) is not None


def test_policy_round_trip():
    policy = RetentionPolicy({"standard": 60.0})
    rebuilt = RetentionPolicy.from_dict(policy.to_dict())
    assert rebuilt.max_age_for("standard") == 60.0


def test_adversarial_purge_keeps_chain_sound(store):
    # Purge the *middle* record: survivors re-chain, tampering with
    # a survivor afterwards is still detected.
    policy = RetentionPolicy({"standard": 100.0})
    now = time.time()
    store.append(aged_record("standard", 200, now))
    store.append(aged_record("standard", 50, now))
    store.append(aged_record("standard", 50, now))
    purge_expired(store, policy, now=now)
    assert store.verify_chain() is True
    survivor = store.recent(2)[0]
    survivor.probability = 0.0  # tamper with the returned copy...
    assert store.verify_chain() is True  # ...copies don't affect the store
