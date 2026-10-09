"""Slice 012 — result invariant hardening.

``DecisionResult`` is the trust boundary between backends and the
application. Every invariant is enforced at construction and pinned
here, including the self-consistency rule
``distribution[value] == probability``.
"""

from __future__ import annotations

import pytest

from hugrgate.client import result_from_dict
from hugrgate.errors import SpecError
from hugrgate.result import DecisionResult


def _ok(**kw):
    base = dict(value="a", probability=0.7,
                distribution={"a": 0.7, "b": 0.3})
    base.update(kw)
    return DecisionResult(**base)


def test_valid_result_constructs():
    r = _ok()
    assert r.value == "a" and r.probability == 0.7


def test_probability_bounds():
    _ok(probability=0.0, value="a", distribution={"a": 0.0, "b": 1.0})
    _ok(probability=1.0, value="a", distribution={"a": 1.0, "b": 0.0})
    with pytest.raises(SpecError, match="out of bounds"):
        _ok(probability=-0.1, distribution={})
    with pytest.raises(SpecError, match="out of bounds"):
        _ok(probability=1.1, distribution={})
    with pytest.raises(SpecError, match="out of bounds"):
        _ok(probability=float("nan"), distribution={})


def test_uncertainty_bounds():
    _ok(uncertainty=0.0)
    _ok(uncertainty=1.0)
    with pytest.raises(SpecError, match="out of bounds"):
        _ok(uncertainty=1.5)


def test_latency_must_be_non_negative():
    _ok(latency_ms=0.0)
    with pytest.raises(SpecError, match="latency_ms"):
        _ok(latency_ms=-1.0)


def test_distribution_must_sum_to_one():
    _ok(distribution={"a": 0.5, "b": 0.5}, probability=0.5, value="a")
    with pytest.raises(SpecError, match="must sum to 1"):
        _ok(distribution={"a": 0.8, "b": 0.3}, probability=0.8, value="a")
    # tolerance boundary: deviations within 1e-6 are floating-point noise
    _ok(distribution={"a": 0.7 + 5e-7, "b": 0.3 - 5e-7},
        probability=0.7 + 5e-7, value="a")


def test_distribution_entries_bounded():
    with pytest.raises(SpecError, match="out of bounds"):
        _ok(distribution={"a": 1.2, "b": -0.2})
    with pytest.raises(SpecError, match="out of bounds"):
        _ok(distribution={"a": float("nan"), "b": 1.0})


def test_distribution_keys_must_be_non_empty_strings():
    with pytest.raises(SpecError, match="non-empty strings"):
        _ok(distribution={1: 0.7, "b": 0.3}, value="a", probability=0.7)
    with pytest.raises(SpecError, match="non-empty strings"):
        _ok(distribution={"": 0.7, "b": 0.3}, value="a", probability=0.7)


def test_distribution_value_consistency():
    # distribution[value] must equal probability
    with pytest.raises(SpecError, match="!= probability"):
        DecisionResult(value="a", probability=0.9,
                       distribution={"a": 0.3, "b": 0.7})
    # consistent pairs construct fine
    DecisionResult(value="b", probability=0.7,
                   distribution={"a": 0.3, "b": 0.7})


def test_consistency_check_skipped_for_multilabel():
    # multilabel values are label lists; each label has its own mass
    r = DecisionResult(value=["a", "b"], probability=0.8,
                       distribution={"a": 0.6, "b": 0.4})
    assert r.value == ["a", "b"]


def test_consistency_check_skipped_for_abstention():
    r = DecisionResult(value=None, probability=0.0)
    assert r.value is None


def test_to_dict_from_dict_round_trip():
    r = _ok(uncertainty=0.2, backend="rules", model="m",
            latency_ms=3.5, calibration_profile="platt",
            fallback_used=True, metadata={"k": "v"})
    rebuilt = result_from_dict(r.to_dict())
    assert rebuilt == r


# --- failure / boundary --------------------------------------------------------

def test_empty_distribution_is_allowed():
    r = DecisionResult(value="a", probability=0.7)
    assert r.distribution == {}


def test_bool_probability_coerces():
    # True == 1.0: accepted, stays in bounds
    r = DecisionResult(value="a", probability=True,
                       distribution={"a": 1.0, "b": 0.0})
    assert r.probability is True
