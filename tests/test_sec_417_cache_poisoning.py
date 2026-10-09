"""Slice 417 — cache-poisoning defenses.

Proves cross-tenant reads and stale-model serving are contained
by the new namespace/model_version key bindings, and that the
pre-existing defenses (spec-type and policy separation,
tamper eviction) hold.
"""

from __future__ import annotations

import pytest

from hugrgate.cache import DecisionCache, cache_key
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.security.cache_poisoning import (
    BoundCache,
    run_poison_suite,
)
from hugrgate.spec import DecisionSpec


def _spec() -> DecisionSpec:
    return DecisionSpec(type="categorical", options=["yes", "no"])


def test_poison_suite_all_contained():
    reports = run_poison_suite()
    assert len(reports) == 5
    failures = [r for r in reports if not r.contained]
    assert failures == [], [(r.attack, r.detail) for r in failures]


def test_namespace_changes_key():
    policy = DecisionPolicy()
    state = {"x": 1}
    k1 = cache_key(state, _spec(), policy)
    k2 = cache_key(state, _spec(), policy, namespace="tenant-a")
    k3 = cache_key(state, _spec(), policy, namespace="tenant-b")
    assert k1 != k2 != k3
    # Historical behavior preserved when unbound.
    assert k1 == cache_key(state, _spec(), policy)


def test_model_version_changes_key():
    policy = DecisionPolicy()
    k1 = cache_key({"x": 1}, _spec(), policy, model_version="1")
    k2 = cache_key({"x": 1}, _spec(), policy, model_version="2")
    assert k1 != k2


def test_bound_cache_round_trip():
    cache: DecisionCache = DecisionCache()
    bound = BoundCache(cache, namespace="t", model_version="3")
    result = DecisionResult(value="yes", probability=0.9,
                            backend="b", model="m")
    assert bound.put({"x": 1}, _spec(), DecisionPolicy(), result)
    hit = bound.get({"x": 1}, _spec(), DecisionPolicy())
    assert hit is not None and hit.value == "yes"


def test_bound_cache_requires_namespace():
    with pytest.raises(ValueError, match="namespace"):
        BoundCache(DecisionCache(), namespace="")


def test_unbound_cache_still_works():
    # Backward compatibility: no namespace/version anywhere.
    cache: DecisionCache = DecisionCache()
    result = DecisionResult(value="no", probability=0.8,
                            backend="b", model="m")
    assert cache.put({"x": 2}, _spec(), DecisionPolicy(), result)
    assert cache.get({"x": 2}, _spec(), DecisionPolicy()).value == "no"


def test_sealed_cache_namespaces(tmp_path):
    from hugrgate.privacy_crypto import EncryptedDecisionCache
    key = b"s" * 32
    cache = EncryptedDecisionCache(key)
    a = BoundCache(cache, namespace="a")
    result = DecisionResult(value="yes", probability=0.9,
                            backend="b", model="m")
    assert a.put({"x": 1}, _spec(), DecisionPolicy(), result)
    assert a.get({"x": 1}, _spec(), DecisionPolicy()).value == "yes"
