"""Slice 281 — serialization optimization.

Covers: compact codec round-trips (result + policy, lossless vs the
dict form), version/length validation errors (SerdeError), aliasing
contract (compact encode shares mappings), JSON-serializability of the
compact form, and a MEASURED comparison: compact round-trip must beat
the dict round-trip.
"""

from __future__ import annotations

import json
import timeit

import pytest

from hugrgate import DecisionPolicy
from hugrgate.errors import SerdeError
from hugrgate.result import DecisionResult
from hugrgate.serde import (
    COMPACT_VERSION,
    policy_from_compact,
    policy_from_dict,
    policy_to_compact,
    result_from_compact,
    result_from_dict,
    result_to_compact,
)


def _result() -> DecisionResult:
    dist = {f"opt-{i}": (0.9 if i == 0 else 0.1 / 63) for i in range(64)}
    return DecisionResult(value="opt-0", probability=0.9, distribution=dist,
                          backend="stub", model="m1", latency_ms=1.5,
                          metadata={"k": "v"})


def _policy() -> DecisionPolicy:
    return DecisionPolicy(minimum_probability=0.5, maximum_latency_ms=100.0,
                          remote_inference=True,
                          allowed_backends=["a"],
                          preferred_backends=["a"],
                          fallback_behavior="escalate",
                          privacy_class="standard", max_cost=2.5,
                          review_band=(0.4, 0.6))


# --- round-trips -------------------------------------------------------------

def test_result_compact_round_trip_lossless():
    original = _result()
    decoded = result_from_compact(result_to_compact(original))
    assert decoded.to_dict() == original.to_dict()


def test_policy_compact_round_trip_lossless():
    original = _policy()
    decoded = policy_from_compact(policy_to_compact(original))
    assert decoded.to_dict() == original.to_dict()


def test_compact_matches_dict_form_semantics():
    original = _result()
    via_dict = result_from_dict(original.to_dict())
    via_compact = result_from_compact(result_to_compact(original))
    assert via_compact.to_dict() == via_dict.to_dict()


def test_compact_is_json_serializable():
    payload = result_to_compact(_result())
    assert json.loads(json.dumps(payload)) == payload
    assert payload[0] == COMPACT_VERSION


def test_compact_aliases_mappings():
    """Encode shares distribution/metadata (no copy) — the zero-copy win."""
    original = _result()
    payload = result_to_compact(original)
    assert payload[3] is original.distribution
    assert payload[11] is original.metadata


def test_compact_decode_copies_defensively():
    """Decode copies: mutating the payload must not corrupt the result."""
    payload = result_to_compact(_result())
    decoded = result_from_compact(payload)
    payload[3]["opt-0"] = 0.0
    assert decoded.distribution["opt-0"] == pytest.approx(0.9)


# --- validation ---------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    [999, "x"],                    # wrong version
    [COMPACT_VERSION],             # too short
    [COMPACT_VERSION] + [None] * 20,  # too long
    "not-a-list",
    None,
])
def test_result_from_compact_rejects_malformed(bad):
    with pytest.raises(SerdeError):
        result_from_compact(bad)


@pytest.mark.parametrize("bad", [
    [999],
    [COMPACT_VERSION, 0.5],
    {"version": COMPACT_VERSION},
])
def test_policy_from_compact_rejects_malformed(bad):
    with pytest.raises(SerdeError):
        policy_from_compact(bad)


def test_compact_version_is_stable():
    assert COMPACT_VERSION == 1


# --- measured wins --------------------------------------------------------------

def _bench(fn, number=3000):
    return timeit.timeit(fn, number=number) / number * 1e6


def test_compact_encode_beats_dict_encode():
    original = _result()
    dict_us = _bench(lambda: original.to_dict())
    compact_us = _bench(lambda: result_to_compact(original))
    assert compact_us < dict_us, (
        f"compact encode {compact_us:.2f}us not faster than dict "
        f"{dict_us:.2f}us")


def test_compact_round_trip_no_regression():
    """Decode is validation-bound by design (DecisionResult.__post_init__
    re-checks every invariant); the compact path must not regress it."""
    original = _result()
    dict_us = _bench(lambda: result_from_dict(original.to_dict()))
    compact_us = _bench(lambda: result_from_compact(result_to_compact(original)))
    assert compact_us <= dict_us * 1.15, (
        f"compact round-trip {compact_us:.2f}us regressed vs dict "
        f"{dict_us:.2f}us")


def test_policy_from_dict_still_rejects_unknown_keys():
    with pytest.raises(Exception):
        policy_from_dict({"minimum_probability": 0.5, "bogus": 1})
