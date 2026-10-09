"""Slice 292 — cache performance tuning.

Correctness regression tests for the tuned hot path:

- cache_key: deterministic, insertion-order-insensitive (including
  nested mappings), sensitive to real changes, tuple/list parity,
  non-serializable values via str(), TypeError parity on
  mixed-type keys.
- _isolated_copy: caller<->cache isolation on put and get (including
  nested metadata), subclass instances keep deepcopy semantics.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.cache import DecisionCache, _isolated_copy, cache_key
from hugrgate.result import DecisionResult


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def _policy():
    return DecisionPolicy(minimum_probability=0.1)


def _result(**kw):
    base = dict(value="a", probability=0.9,
                distribution={"a": 0.9, "b": 0.1},
                backend="bench", latency_ms=1.0)
    base.update(kw)
    return DecisionResult(**base)


# --- cache_key ---------------------------------------------------------------------

def test_key_deterministic():
    state = {"x": 1, "y": [1, 2]}
    k1 = cache_key(state, _spec(), _policy())
    k2 = cache_key(state, _spec(), _policy())
    assert k1 == k2 and len(k1) == 64


def test_key_order_insensitive_top_level():
    s1 = {"a": 1, "b": 2, "c": 3}
    s2 = {"c": 3, "a": 1, "b": 2}
    assert cache_key(s1, _spec(), _policy()) == \
        cache_key(s2, _spec(), _policy())


def test_key_order_insensitive_nested():
    s1 = {"outer": {"a": 1, "b": [3, {"z": 1, "y": 2}]}, "k": "v"}
    s2 = {"k": "v", "outer": {"b": [3, {"y": 2, "z": 1}], "a": 1}}
    assert cache_key(s1, _spec(), _policy()) == \
        cache_key(s2, _spec(), _policy())


def test_key_sensitive_to_changes():
    base = cache_key({"a": 1}, _spec(), _policy())
    assert cache_key({"a": 2}, _spec(), _policy()) != base
    assert cache_key({"a": 1, "b": 0}, _spec(), _policy()) != base
    other_spec = DecisionSpec(type="categorical", options=["a", "c"])
    assert cache_key({"a": 1}, other_spec, _policy()) != base
    other_policy = DecisionPolicy(minimum_probability=0.5)
    assert cache_key({"a": 1}, _spec(), other_policy) != base


def test_key_tuple_list_parity():
    # json serializes tuples as arrays; tuples and lists of equal
    # items hashed equal before the tuning and still do.
    assert cache_key({"a": (1, 2)}, _spec(), _policy()) == \
        cache_key({"a": [1, 2]}, _spec(), _policy())


def test_key_non_serializable_uses_str():
    class _Strange:
        def __str__(self):
            return "obj!"

    k = cache_key({"o": _Strange(), "s": {1, 2}}, _spec(), _policy())
    assert len(k) == 64  # no crash, stable shape


def test_key_mixed_type_keys_raise_typeerror():
    # Parity: sort_keys=True raised TypeError on unorderable keys;
    # the Python-side sort raises it too.
    with pytest.raises(TypeError):
        cache_key({1: "a", "b": "c"}, _spec(), _policy())


# --- _isolated_copy ------------------------------------------------------------------

def test_put_isolates_caller_mutation():
    cache = DecisionCache()
    res = _result(metadata={"route": ["x"]})
    cache.put({"a": 1}, _spec(), _policy(), res)
    res.distribution["a"] = 0.0
    res.metadata["route"].append("MUT")
    got = cache.get({"a": 1}, _spec(), _policy())
    assert got.distribution == {"a": 0.9, "b": 0.1}
    assert got.metadata == {"route": ["x"]}


def test_get_isolates_cache_mutation():
    cache = DecisionCache()
    cache.put({"a": 1}, _spec(), _policy(),
              _result(metadata={"route": ["x"]}))
    got = cache.get({"a": 1}, _spec(), _policy())
    got.distribution["zzz"] = 1.0
    got.metadata["route"].append("MUT")
    again = cache.get({"a": 1}, _spec(), _policy())
    assert "zzz" not in again.distribution
    assert again.metadata == {"route": ["x"]}


def test_isolated_copy_preserves_value_and_type():
    res = _result()
    c = _isolated_copy(res)
    assert type(c) is DecisionResult
    assert c == res
    assert c is not res
    assert c.distribution == res.distribution
    assert c.distribution is not res.distribution


def test_isolated_copy_subclass_uses_deepcopy():
    class Sub(DecisionResult):
        extra: object = None

    sub = Sub(value="a", probability=0.9,
              distribution={"a": 0.9, "b": 0.1}, backend="b",
              latency_ms=1.0)
    sub.extra = {"nested": [1, 2]}
    c = _isolated_copy(sub)
    assert type(c) is Sub
    assert c.extra == {"nested": [1, 2]}
    assert c.extra is not sub.extra
