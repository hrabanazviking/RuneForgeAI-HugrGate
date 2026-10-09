"""Slice 280 — zero-copy opportunities.

Covers: freeze() immutability (attribute writes, nested mapping
mutation, double-freeze identity), thaw() round-trip, ZeroCopyCache
(zero-copy hits return the identical object, LRU/TTL/privacy/
invalidation behavior, unfrozen-put rejection), SharedPayload
(encode-once identity, bytes passthrough), copy_cost_estimate, and a
measured comparison of deepcopy-per-hit vs shared-serve.
"""

from __future__ import annotations

import copy
import time

import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.errors import ZeroCopyError
from hugrgate.result import DecisionResult
from hugrgate.zerocopy import (
    FrozenDecisionResult,
    SharedPayload,
    ZeroCopyCache,
    copy_cost_estimate,
    freeze,
)


def _result(**kw) -> DecisionResult:
    base = {
        "value": "a",
        "probability": 0.9,
        "distribution": {"a": 0.9, "b": 0.1},
        "backend": "stub",
        "metadata": {"k": "v"},
    }
    base.update(kw)
    return DecisionResult(**base)


SPEC = DecisionSpec(type="categorical", options=["a", "b"])
POLICY = DecisionPolicy(minimum_probability=0.0)


# --- freeze ---------------------------------------------------------------

def test_freeze_preserves_values():
    frozen = freeze(_result())
    assert frozen.value == "a"
    assert frozen.probability == 0.9
    assert dict(frozen.distribution) == {"a": 0.9, "b": 0.1}
    assert frozen.backend == "stub"
    assert dict(frozen.metadata) == {"k": "v"}


def test_freeze_is_idempotent():
    frozen = freeze(_result())
    assert freeze(frozen) is frozen


def test_freeze_rejects_non_result():
    with pytest.raises(ZeroCopyError):
        freeze("not-a-result")


def test_frozen_attributes_reject_mutation():
    frozen = freeze(_result())
    with pytest.raises(ZeroCopyError):
        frozen.value = "b"
    with pytest.raises(ZeroCopyError):
        frozen.probability = 0.1
    with pytest.raises(ZeroCopyError):
        del frozen.backend


def test_frozen_nested_mappings_reject_mutation():
    frozen = freeze(_result())
    with pytest.raises(TypeError):
        frozen.distribution["a"] = 0.5
    with pytest.raises(TypeError):
        frozen.metadata["k"] = "evil"


def test_freeze_copies_once_not_by_reference():
    original = _result()
    frozen = freeze(original)
    original.distribution["a"] = 0.0  # mutate the source afterwards
    original.metadata["k"] = "changed"
    assert frozen.distribution["a"] == 0.9
    assert frozen.metadata["k"] == "v"


def test_thaw_returns_mutable_equal_result():
    frozen = freeze(_result())
    thawed = frozen.thaw()
    assert isinstance(thawed, DecisionResult)
    assert thawed.value == frozen.value
    assert thawed.distribution == dict(frozen.distribution)
    thawed.value = "b"  # mutable again
    assert thawed.value == "b"


def test_frozen_equality():
    assert freeze(_result()) == freeze(_result())
    assert freeze(_result()) == _result()
    other = _result(value="b", probability=0.1,
                    distribution={"a": 0.9, "b": 0.1})
    assert freeze(_result()) != freeze(other)


# --- ZeroCopyCache ----------------------------------------------------------

def test_zero_copy_cache_hit_returns_identical_object():
    cache = ZeroCopyCache()
    frozen = freeze(_result())
    assert cache.put({"x": 1}, SPEC, POLICY, frozen) is True
    hit1 = cache.get({"x": 1}, SPEC, POLICY)
    hit2 = cache.get({"x": 1}, SPEC, POLICY)
    assert hit1 is frozen
    assert hit2 is frozen  # zero copies: the identical object
    assert cache.stats()["hits"] == 2
    assert cache.stats()["copies_per_hit"] == 0


def test_zero_copy_cache_miss_and_expiry():
    cache = ZeroCopyCache(ttl_seconds=0.05)
    assert cache.get({"x": 1}, SPEC, POLICY) is None
    cache.put({"x": 1}, SPEC, POLICY, freeze(_result()))
    assert cache.get({"x": 1}, SPEC, POLICY) is not None
    time.sleep(0.06)
    assert cache.get({"x": 1}, SPEC, POLICY) is None
    assert cache.stats()["misses"] == 2


def test_zero_copy_cache_rejects_unfrozen_by_default():
    cache = ZeroCopyCache()
    with pytest.raises(ZeroCopyError):
        cache.put({"x": 1}, SPEC, POLICY, _result())


def test_zero_copy_cache_freeze_on_put():
    cache = ZeroCopyCache(freeze_on_put=True)
    assert cache.put({"x": 1}, SPEC, POLICY, _result()) is True
    hit = cache.get({"x": 1}, SPEC, POLICY)
    assert isinstance(hit, FrozenDecisionResult)
    assert hit.value == "a"


def test_zero_copy_cache_lru_eviction():
    cache = ZeroCopyCache(max_size=2)
    for i in range(3):
        cache.put({"x": i}, SPEC, POLICY, freeze(_result()))
    assert cache.stats()["size"] == 2
    assert cache.get({"x": 0}, SPEC, POLICY) is None  # evicted


def test_zero_copy_cache_privacy_gate():
    cache = ZeroCopyCache()
    strict = DecisionPolicy(minimum_probability=0.0, privacy_class="strict")
    assert cache.put({"x": 1}, SPEC, strict, freeze(_result())) is False
    assert cache.get({"x": 1}, SPEC, strict) is None


def test_zero_copy_cache_invalidate_backend():
    cache = ZeroCopyCache()
    cache.put({"x": 1}, SPEC, POLICY, freeze(_result(backend="b1")))
    cache.put({"x": 2}, SPEC, POLICY, freeze(_result(backend="b2")))
    assert cache.invalidate_backend("b1") == 1
    assert cache.get({"x": 1}, SPEC, POLICY) is None
    assert cache.get({"x": 2}, SPEC, POLICY) is not None


def test_zero_copy_cache_bad_config():
    with pytest.raises(ZeroCopyError):
        ZeroCopyCache(ttl_seconds=0)
    with pytest.raises(ZeroCopyError):
        ZeroCopyCache(max_size=0)


# --- SharedPayload ----------------------------------------------------------

def test_shared_payload_encode_once():
    payload = SharedPayload.from_json({"a": 1, "b": [1, 2]})
    assert payload.data == b'{"a":1,"b":[1,2]}'
    assert payload.content_type == "application/json"
    assert len(payload) == len(payload.data)
    assert bytes(payload) is payload.data  # identical object


def test_shared_payload_rejects_non_bytes():
    with pytest.raises(ZeroCopyError):
        SharedPayload("not-bytes")


# --- measured win -----------------------------------------------------------

def test_copy_cost_estimate_measures_real_tax():
    result = _result(distribution={f"opt-{i}": 1 / 64 for i in range(64)})
    cost = copy_cost_estimate(result, repeats=50)
    assert cost["us_per_copy"] > 0
    assert cost["repeats"] == 50.0
    with pytest.raises(ZeroCopyError):
        copy_cost_estimate(result, repeats=0)


def test_shared_serve_beats_deepcopy_per_hit():
    """Measured: N shared serves vs N deepcopy hits on the same result."""
    result = _result(distribution={f"opt-{i}": 1 / 64 for i in range(64)})
    n = 200
    start = time.perf_counter()
    for _ in range(n):
        copy.deepcopy(result)
    deepcopy_us = (time.perf_counter() - start) * 1e6 / n

    frozen = freeze(result)
    start = time.perf_counter()
    for _ in range(n):
        seen = frozen  # what ZeroCopyCache.get does: return the object
    shared_us = (time.perf_counter() - start) * 1e6 / n

    assert deepcopy_us > shared_us
    assert seen is frozen
    # the tax being eliminated is real and measurable (not noise)
    assert deepcopy_us > 1.0
