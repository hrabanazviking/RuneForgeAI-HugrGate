"""Slice 013 — policy invariant hardening.

Policy-domain configuration errors now raise ``PolicyError`` (not the
generic ``ValueError``), and ``DecisionPolicy.review_band`` shape is
validated explicitly. The gate-precedence rules are pinned.
"""

from __future__ import annotations

import pytest

from hugrgate.abstain import abstain, apply_abstention_policy, mark_for_review
from hugrgate.errors import PolicyError
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec
from hugrgate.threshold import (
    NumericBand, ThresholdConfig, apply_thresholds,
    classify_numeric_band, ordinal_cumulative_probability,
)

CAT_SPEC = DecisionSpec(type="categorical", options=["a", "b", "c"])
ORD_SPEC = DecisionSpec(type="ordinal", levels=["low", "moderate", "high"])


def _res(value="a", probability=0.7, **kw):
    rest = (1.0 - probability) / 2
    base = dict(value=value, probability=probability,
                distribution={"a": probability, "b": rest, "c": rest})
    base.update(kw)
    return DecisionResult(**base)


# --- taxonomy: policy-domain errors are PolicyError --------------------------

def test_numeric_band_lo_gt_hi_is_policy_error():
    with pytest.raises(PolicyError):
        NumericBand("bad", lo=5.0, hi=1.0)
    with pytest.raises(PolicyError):
        NumericBand("bad", 0.0, 1.0, min_probability=1.5)


def test_threshold_config_rejects_bad_gates():
    with pytest.raises(PolicyError):
        ThresholdConfig(per_option={"a": 1.5})
    with pytest.raises(PolicyError):
        ThresholdConfig(per_option={"": 0.5})
    with pytest.raises(PolicyError):
        ThresholdConfig(ordinal_minimum=("", 0.5))
    with pytest.raises(PolicyError):
        ThresholdConfig(ordinal_minimum=("moderate", 2.0))
    with pytest.raises(PolicyError):
        ThresholdConfig(global_minimum=-0.1)


def test_ordinal_cumulative_rejects_wrong_spec_and_level():
    r = _res("moderate", 0.6)
    with pytest.raises(PolicyError):
        ordinal_cumulative_probability(r, CAT_SPEC, "moderate")
    with pytest.raises(PolicyError):
        ordinal_cumulative_probability(r, ORD_SPEC, "extreme")


def test_review_band_malformed():
    with pytest.raises(PolicyError, match=r"\(lo, hi\) pair"):
        DecisionPolicy(review_band=(0.1, 0.2, 0.3))
    with pytest.raises(PolicyError):
        DecisionPolicy(review_band=(0.5, 0.1))


# --- gate precedence ---------------------------------------------------------

def test_global_minimum_overrides_policy_floor():
    # policy floor is high; config override lowers it -> accepted
    policy = DecisionPolicy(minimum_probability=0.9)
    config = ThresholdConfig(global_minimum=0.5)
    out = apply_thresholds(_res(probability=0.7), CAT_SPEC, config, policy)
    assert out.accepted is True
    # without the override the policy floor abstains
    out = apply_thresholds(_res(probability=0.7), CAT_SPEC,
                           ThresholdConfig(), policy)
    assert out.accepted is False
    assert "below threshold floor" in out.metadata["abstain_reason"]


def test_per_option_gate_names_itself():
    config = ThresholdConfig(per_option={"a": 0.99})
    out = apply_thresholds(_res(probability=0.7), CAT_SPEC, config)
    assert out.accepted is False
    assert "per-option" in out.metadata["abstain_reason"]
    assert out.value is None  # abstentions carry no value


def test_abstention_result_shape():
    out = abstain(CAT_SPEC, reason="t", backend="b")
    assert out.value is None and out.accepted is False
    assert out.uncertainty == 1.0
    assert out.metadata["policy_verdict"] == "abstain"
    assert abs(sum(out.distribution.values()) - 1.0) < 1e-9  # uniform


def test_review_preserves_value_and_probability():
    r = _res(probability=0.55)
    out = mark_for_review(r, "human eyes")
    assert out.value == "a" and out.probability == 0.55
    assert out.accepted is False
    assert out.metadata["policy_verdict"] == "review"


def test_apply_abstention_policy_verdicts():
    policy = DecisionPolicy(minimum_probability=0.5,
                            review_band=(0.5, 0.7))
    assert apply_abstention_policy(
        _res(probability=0.8), CAT_SPEC, policy).accepted is True
    rev = apply_abstention_policy(_res(probability=0.6), CAT_SPEC, policy)
    assert rev.metadata["policy_verdict"] == "review"
    abs_ = apply_abstention_policy(_res(probability=0.4), CAT_SPEC, policy)
    assert abs_.accepted is False and abs_.value is None


def test_numeric_band_edge_is_inclusive():
    bands = [NumericBand("normal", 36.0, 37.5),
             NumericBand("fever", 37.5, 42.0)]
    assert classify_numeric_band(37.5, bands).name == "normal"  # first match
