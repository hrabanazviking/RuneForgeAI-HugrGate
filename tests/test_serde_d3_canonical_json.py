"""Slice D3: canonical JSON (to_canonical_json / from_canonical_json)."""

import json

import pytest

from hugrgate.serde import from_canonical_json, to_canonical_json


def _nested(value=float(1) / 3):
    return {
        "zeta": [value, 2.5, {"inner": value, "flag": True}],
        "alpha": (1, None, "x", [value]),
        "mu": {"b": 1, "a": [False, {"z": value}]},
    }


def test_round_trip():
    obj = _nested()
    decoded = from_canonical_json(to_canonical_json(obj))
    assert decoded == from_canonical_json(json.dumps(_nested(0.333333)))


def test_key_insertion_order_irrelevant():
    a = {"b": 1, "a": {"y": 2, "x": 3}, "c": [1, {"q": 1, "p": 2}]}
    b = {"c": [1, {"q": 1, "p": 2}], "a": {"x": 3, "y": 2}, "b": 1}
    assert to_canonical_json(a) == to_canonical_json(b)


def test_float_noise_normalized():
    assert to_canonical_json({"p": 1 / 3}) == to_canonical_json({"p": 0.333333})
    assert to_canonical_json({"p": 1 / 3}) == '{"p":0.333333}'


def test_compact_separators_and_sorted_keys():
    s = to_canonical_json({"b": 1, "a": 2})
    assert s == '{"a":2,"b":1}'
    assert " " not in s


def test_nested_tuples_and_non_float_scalars_untouched():
    s = to_canonical_json({"t": (1, True, None, "s", (2.0,))})
    assert json.loads(s) == {"t": [1, True, None, "s", [2.0]]}
    assert to_canonical_json({"i": 5, "f": 2.0, "b": False, "n": None}) == (
        '{"b":false,"f":2.0,"i":5,"n":null}'
    )


def test_non_json_native_raises_typeerror():
    with pytest.raises(TypeError):
        to_canonical_json({"s": {1, 2, 3}})
    with pytest.raises(TypeError):
        to_canonical_json(object())
