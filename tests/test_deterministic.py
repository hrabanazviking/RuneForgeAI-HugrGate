"""Tests for Batch B (Slices 11-20): the deterministic core."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from hugrgate import (
    Abstention,
    Backend,
    BackendError,
    DecisionPolicy,
    DecisionResult,
    DecisionSpec,
    PolicyError,
    SpecError,
    TimeoutError,
)
from hugrgate.abstain import abstain, apply_abstention_policy, mark_for_review
from hugrgate.backends.rules import Rule, RuleBackend
from hugrgate.circuit import CLOSED, HALF_OPEN, OPEN, CircuitBreaker, CircuitRegistry
from hugrgate.fallback import FallbackChain
from hugrgate.health import HealthMonitor
from hugrgate.threshold import (
    NumericBand,
    ThresholdConfig,
    apply_thresholds,
    classify_numeric_band,
    ordinal_cumulative_probability,
)
from hugrgate.timeout import (
    TimeoutBackend,
    deadline_ms_for,
    evaluate_with_timeout,
    run_with_deadline,
)

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

CAT_SPEC = DecisionSpec(type="categorical", options=["a", "b", "c"])
BIN_SPEC = DecisionSpec(type="binary", statement="Is it so?")
ORD_SPEC = DecisionSpec(type="ordinal", levels=["low", "moderate", "high"])
NUM_SPEC = DecisionSpec(type="numeric", minimum=0.0, maximum=100.0)


class OkBackend(Backend):
    name = "ok"

    def __init__(self, value="a", probability=0.9, name="ok"):
        self.name = name
        self._value = value
        self._probability = probability

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        others = [o for o in spec.options if o != self._value]
        dist = {self._value: self._probability}
        for o in others:
            dist[o] = (1 - self._probability) / len(others)
        return DecisionResult(value=self._value, probability=self._probability,
                              distribution=dist, backend=self.name)


class FailBackend(Backend):
    name = "fail"

    def __init__(self, name="fail", error=None):
        self.name = name
        self._error = error or BackendError("boom")

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        raise self._error


class AbstainBackend(Backend):
    name = "abstainer"

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        raise Abstention("nope", reason="test_abstain")


class SlowBackend(Backend):
    name = "slow"

    def __init__(self, delay_s=0.3):
        self.delay_s = delay_s

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def estimated_latency(self):
        return self.delay_s * 1000

    def evaluate(self, state, spec, context=None):
        time.sleep(self.delay_s)
        return OkBackend().evaluate(state, spec, context)


def rule_backend(*dicts, **kwargs):
    return RuleBackend.from_dicts(list(dicts), **kwargs)


# --------------------------------------------------------------------------
# Slice 11 — predicates
# --------------------------------------------------------------------------

class TestPredicates:
    @pytest.mark.parametrize("op,field_value,rule_value,expected", [
        ("eq", 90, 90, True), ("eq", 90, 91, False),
        ("ne", 90, 91, True), ("ne", 90, 90, False),
        ("gt", 91, 90, True), ("gt", 90, 90, False),
        ("gte", 90, 90, True), ("gte", 89, 90, False),
        ("lt", 89, 90, True), ("lt", 90, 90, False),
        ("lte", 90, 90, True), ("lte", 91, 90, False),
        ("in", "b", ["a", "b"], True), ("in", "z", ["a", "b"], False),
        ("contains", ["x", "y"], "y", True),
        ("contains", ["x", "y"], "z", False),
        ("contains", "hello world", "world", True),
        ("contains", {"k": 1}, "k", True),
        ("exists", "anything", True, True),
    ])
    def test_operators(self, op, field_value, rule_value, expected):
        cond = {"field": "f", op: rule_value}
        state = {"f": field_value}  # field present; exists -> True
        b = rule_backend({"if": cond, "then": "a", "confidence": 1.0},
                         {"default": "b", "confidence": 1.0})
        result = b.evaluate(state, CAT_SPEC)
        assert (result.value == "a") == expected

    def test_exists_absent(self):
        b = rule_backend({"if": {"field": "f", "exists": True}, "then": "a"},
                         {"default": "b"})
        assert b.evaluate({}, CAT_SPEC).value == "b"
        assert b.evaluate({"f": 1}, CAT_SPEC).value == "a"

    def test_exists_explicit_false(self):
        b = rule_backend({"if": {"field": "f", "exists": False}, "then": "a"},
                         {"default": "b"})
        assert b.evaluate({}, CAT_SPEC).value == "a"
        assert b.evaluate({"f": 1}, CAT_SPEC).value == "b"

    def test_missing_field_ne_matches(self):
        b = rule_backend({"if": {"field": "nope", "ne": "x"}, "then": "a"},
                         {"default": "b"})
        assert b.evaluate({}, CAT_SPEC).value == "a"

    def test_missing_field_comparisons_do_not_match(self):
        b = rule_backend({"if": {"field": "nope", "gt": 5}, "then": "a"},
                         {"default": "b"})
        assert b.evaluate({}, CAT_SPEC).value == "b"

    def test_type_error_comparison_does_not_match(self):
        b = rule_backend({"if": {"field": "f", "gt": 90}, "then": "a"},
                         {"default": "b"})
        assert b.evaluate({"f": "not-a-number"}, CAT_SPEC).value == "b"

    def test_dotted_field_path(self):
        b = rule_backend({"if": {"field": "source.ip", "eq": "1.2.3.4"},
                          "then": "a"},
                         {"default": "b"})
        assert b.evaluate({"source": {"ip": "1.2.3.4"}}, CAT_SPEC).value == "a"
        assert b.evaluate({"source": {}}, CAT_SPEC).value == "b"

    def test_explicit_op_value_form(self):
        b = rule_backend(
            {"if": {"field": "t", "op": "gte", "value": 90}, "then": "a"},
            {"default": "b"})
        assert b.evaluate({"t": 95}, CAT_SPEC).value == "a"

    def test_all_any_not_composition(self):
        b = rule_backend(
            {"if": {"all": [{"field": "a", "gt": 1},
                            {"any": [{"field": "b", "eq": 2},
                                     {"not": {"field": "c", "eq": 3}}]}]},
             "then": "a"},
            {"default": "b"})
        assert b.evaluate({"a": 5, "b": 2, "c": 9}, CAT_SPEC).value == "a"
        assert b.evaluate({"a": 5, "b": 0, "c": 3}, CAT_SPEC).value == "b"
        assert b.evaluate({"a": 0, "b": 2, "c": 9}, CAT_SPEC).value == "b"

    def test_first_match_wins(self):
        b = rule_backend(
            {"if": {"field": "x", "eq": 1}, "then": "a"},
            {"if": {"field": "x", "eq": 1}, "then": "b"})
        assert b.evaluate({"x": 1}, CAT_SPEC).value == "a"

    def test_no_match_no_default_abstains(self):
        b = rule_backend({"if": {"field": "x", "eq": 1}, "then": "a"})
        with pytest.raises(Abstention) as exc:
            b.evaluate({"x": 2}, CAT_SPEC)
        assert exc.value.reason == "no_rule_matched"

    def test_unknown_operator_raises(self):
        b = rule_backend({"if": {"field": "x", "frobnicates": 1}, "then": "a"})
        with pytest.raises(SpecError):
            b.evaluate({"x": 1}, CAT_SPEC)

    def test_confidence_out_of_bounds_rejected(self):
        with pytest.raises(SpecError):
            Rule(condition={"field": "x", "eq": 1}, then="a", confidence=1.5)

    def test_rule_needs_condition_or_default(self):
        with pytest.raises(SpecError):
            Rule.from_dict({"then": "a"})


# --------------------------------------------------------------------------
# Slice 12 — decision tables
# --------------------------------------------------------------------------

class TestDecisionTables:
    def test_priority_ordering(self):
        b = rule_backend(
            {"name": "low-prio", "priority": 1,
             "if": {"field": "x", "eq": 1}, "then": "a"},
            {"name": "high-prio", "priority": 99,
             "if": {"field": "x", "eq": 1}, "then": "b"})
        result = b.evaluate({"x": 1}, CAT_SPEC)
        assert result.value == "b"
        assert result.metadata["matched_rule"] == "high-prio"

    def test_default_rule_evaluated_last(self):
        b = rule_backend(
            {"default": "c", "confidence": 0.5, "priority": 1000},
            {"if": {"field": "x", "eq": 1}, "then": "a", "confidence": 0.9})
        result = b.evaluate({"x": 1}, CAT_SPEC)
        assert result.value == "a"
        assert not result.metadata["default_used"]
        result2 = b.evaluate({"x": 2}, CAT_SPEC)
        assert result2.value == "c"
        assert result2.metadata["default_used"]

    def test_when_alias(self):
        b = rule_backend({"when": {"field": "x", "eq": 1}, "then": "a"},
                         {"default": "b"})
        assert b.evaluate({"x": 1}, CAT_SPEC).value == "a"

    def test_yaml_text_mapping_form(self):
        text = """
name: demo
rules:
  - name: hot
    priority: 10
    if: {field: temp, gt: 90}
    then: a
    confidence: 0.99
  - {default: b, confidence: 0.4}
"""
        b = RuleBackend.from_yaml_text(text)
        assert b.name == "demo"
        assert len(b) == 2
        assert b.evaluate({"temp": 100}, CAT_SPEC).value == "a"
        assert b.evaluate({"temp": 10}, CAT_SPEC).value == "b"

    def test_yaml_text_list_form(self):
        text = "- {if: {field: x, eq: 1}, then: a}\n- {default: b}\n"
        b = RuleBackend.from_yaml_text(text)
        assert b.evaluate({"x": 1}, CAT_SPEC).value == "a"

    def test_yaml_file(self, tmp_path):
        p = tmp_path / "rules.yaml"
        p.write_text("rules:\n  - {if: {field: x, eq: 1}, then: a}\n")
        b = RuleBackend.from_yaml_file(str(p))
        assert b.evaluate({"x": 1}, CAT_SPEC).value == "a"

    def test_yaml_invalid_shape_rejected(self):
        with pytest.raises(SpecError):
            RuleBackend.from_yaml_text("just: a-string-value: : :")

    def test_to_dicts_round_trip(self):
        b = rule_backend({"name": "r1", "priority": 5,
                          "if": {"field": "x", "gte": 3},
                          "then": "a", "confidence": 0.8},
                         {"default": "b", "confidence": 0.5})
        b2 = RuleBackend.from_dicts(b.to_dicts())
        assert b2.evaluate({"x": 10}, CAT_SPEC).value == "a"
        assert b2.evaluate({"x": 0}, CAT_SPEC).value == "b"


# --------------------------------------------------------------------------
# Slice 13 — confidence & distribution
# --------------------------------------------------------------------------

class TestConfidenceDistribution:
    def test_distribution_sums_to_one(self):
        b = rule_backend({"if": {"field": "x", "eq": 1}, "then": "a",
                          "confidence": 0.7})
        dist = b.evaluate({"x": 1}, CAT_SPEC).distribution
        assert abs(sum(dist.values()) - 1.0) < 1e-9

    def test_winner_gets_confidence_remainder_split(self):
        b = rule_backend({"if": {"field": "x", "eq": 1}, "then": "a",
                          "confidence": 0.7})
        dist = b.evaluate({"x": 1}, CAT_SPEC).distribution
        assert dist["a"] == pytest.approx(0.7)
        assert dist["b"] == pytest.approx(0.15)
        assert dist["c"] == pytest.approx(0.15)

    def test_full_confidence_zero_remainder(self):
        b = rule_backend({"if": {"field": "x", "eq": 1}, "then": "a",
                          "confidence": 1.0})
        dist = b.evaluate({"x": 1}, CAT_SPEC).distribution
        assert dist["a"] == pytest.approx(1.0)
        assert dist["b"] == pytest.approx(0.0)

    def test_uncertainty_is_one_minus_confidence(self):
        b = rule_backend({"if": {"field": "x", "eq": 1}, "then": "a",
                          "confidence": 0.8})
        result = b.evaluate({"x": 1}, CAT_SPEC)
        assert result.probability == pytest.approx(0.8)
        assert result.uncertainty == pytest.approx(0.2)

    def test_binary_bool_normalization(self):
        b = rule_backend({"if": {"field": "x", "eq": 1}, "then": True,
                          "confidence": 0.9})
        result = b.evaluate({"x": 1}, BIN_SPEC)
        assert result.value == "true"
        assert result.distribution["true"] == pytest.approx(0.9)
        assert result.distribution["false"] == pytest.approx(0.1)

    def test_supports_categorical_binary_ordinal(self):
        b = rule_backend()
        assert b.supports(CAT_SPEC)
        assert b.supports(BIN_SPEC)
        assert b.supports(ORD_SPEC)
        assert not b.supports(NUM_SPEC)
        assert not b.supports(
            DecisionSpec(type="multilabel", labels=["x", "y"]))

    def test_unsupported_spec_raises(self):
        b = rule_backend({"default": "a"})
        from hugrgate.errors import BackendUnavailable
        with pytest.raises(BackendUnavailable):
            b.evaluate({"v": 5}, NUM_SPEC)

    def test_outcome_outside_spec_space_raises(self):
        b = rule_backend({"if": {"field": "x", "eq": 1}, "then": "zzz"})
        with pytest.raises(BackendError):
            b.evaluate({"x": 1}, CAT_SPEC)

    def test_ordinal_rule(self):
        b = rule_backend({"if": {"field": "sev", "gte": 7}, "then": "high",
                          "confidence": 0.85},
                         {"default": "low", "confidence": 0.6})
        r = b.evaluate({"sev": 9}, ORD_SPEC)
        assert r.value == "high"
        assert abs(sum(r.distribution.values()) - 1.0) < 1e-9


# --------------------------------------------------------------------------
# Slice 14 — fallback chain
# --------------------------------------------------------------------------

class TestFallbackChain:
    def test_first_backend_wins_no_fallback(self):
        chain = FallbackChain([OkBackend("a"), OkBackend("b")])
        result = chain.evaluate({}, CAT_SPEC)
        assert result.value == "a"
        assert result.fallback_used is False

    def test_failover_to_next_backend(self):
        chain = FallbackChain([FailBackend(), OkBackend("b")])
        result = chain.evaluate({}, CAT_SPEC)
        assert result.value == "b"
        assert result.fallback_used is True
        trace = result.metadata["fallback_trace"]
        assert [t["backend"] for t in trace] == ["fail", "ok"]
        assert trace[0]["outcome"] == "failed"

    def test_timeout_triggers_failover(self):
        slow = TimeoutBackend(SlowBackend(delay_s=0.3),
                              explicit_deadline_ms=50.0)
        chain = FallbackChain([slow, OkBackend("b")])
        result = chain.evaluate({}, CAT_SPEC)
        assert result.value == "b"
        assert result.fallback_used is True

    def test_abstention_propagates_not_swallowed(self):
        chain = FallbackChain([AbstainBackend(), OkBackend("b")])
        with pytest.raises(Abstention):
            chain.evaluate({}, CAT_SPEC)

    def test_exhausted_abstain_behavior(self):
        chain = FallbackChain([FailBackend("f1"), FailBackend("f2")])
        with pytest.raises(Abstention) as exc:
            chain.evaluate({}, CAT_SPEC)
        assert exc.value.reason == "all_backends_failed"

    def test_exhausted_safe_default(self):
        policy = DecisionPolicy(fallback_behavior="safe_default")
        chain = FallbackChain([FailBackend()], policy=policy,
                              safe_default="c")
        result = chain.evaluate({}, CAT_SPEC)
        assert result.value == "c"
        assert result.probability == 1.0
        assert result.fallback_used is True
        assert result.metadata["safe_default_used"] is True

    def test_exhausted_escalate(self):
        policy = DecisionPolicy(fallback_behavior="escalate")
        chain = FallbackChain([FailBackend()], policy=policy)
        with pytest.raises(Abstention) as exc:
            chain.evaluate({}, CAT_SPEC)
        assert exc.value.reason == "escalation_required"

    def test_safe_default_outside_space_raises(self):
        policy = DecisionPolicy(fallback_behavior="safe_default")
        chain = FallbackChain([FailBackend()], policy=policy,
                              safe_default="nope")
        with pytest.raises(BackendError):
            chain.evaluate({}, CAT_SPEC)

    def test_safe_default_requires_value(self):
        policy = DecisionPolicy(fallback_behavior="safe_default")
        with pytest.raises(PolicyError):
            FallbackChain([OkBackend()], policy=policy)

    def test_empty_chain_rejected(self):
        with pytest.raises(PolicyError):
            FallbackChain([])

    def test_supports_any_member(self):
        chain = FallbackChain([FailBackend(), OkBackend()])
        assert chain.supports(CAT_SPEC)
        assert not chain.supports(NUM_SPEC)

    def test_open_circuit_skips_backend(self):
        circuits = CircuitRegistry(failure_threshold=1)
        breaker = circuits.get("fail")
        breaker.record_failure()
        assert breaker.state == OPEN
        chain = FallbackChain([FailBackend(), OkBackend("b")],
                              circuits=circuits)
        result = chain.evaluate({}, CAT_SPEC)
        assert result.value == "b"
        trace = result.metadata["fallback_trace"]
        assert trace[0]["outcome"] == "skipped"
        assert trace[0]["reason"] == "circuit_open"

    def test_success_reports_to_breaker(self):
        circuits = CircuitRegistry()
        chain = FallbackChain([OkBackend("a")], circuits=circuits)
        chain.evaluate({}, CAT_SPEC)
        assert circuits.get("ok").state == CLOSED


# --------------------------------------------------------------------------
# Slice 15 — abstention
# --------------------------------------------------------------------------

class TestAbstention:
    def test_abstain_result_shape(self):
        r = abstain(CAT_SPEC, reason="too_unsure", backend="rules")
        assert r.value is None
        assert r.accepted is False
        assert r.probability == 0.0
        assert r.uncertainty == 1.0
        assert r.backend == "rules"
        assert r.metadata["abstain_reason"] == "too_unsure"
        assert abs(sum(r.distribution.values()) - 1.0) < 1e-9
        assert set(r.distribution) == {"a", "b", "c"}

    def test_abstain_numeric_empty_distribution(self):
        r = abstain(NUM_SPEC, reason="x")
        assert r.value is None
        assert r.distribution == {}

    def test_mark_for_review_preserves_value(self):
        original = DecisionResult(value="a", probability=0.6,
                                  distribution={"a": 0.6, "b": 0.2, "c": 0.2},
                                  backend="rules")
        r = mark_for_review(original, reason="band", reviewer="volmarr")
        assert r.value == "a"
        assert r.probability == 0.6
        assert r.accepted is False
        assert r.metadata["policy_verdict"] == "review"
        assert r.metadata["review_reason"] == "band"
        assert r.metadata["reviewer"] == "volmarr"

    def test_apply_policy_accept(self):
        policy = DecisionPolicy(minimum_probability=0.5)
        r = DecisionResult(value="a", probability=0.9,
                           distribution={"a": 0.9, "b": 0.05, "c": 0.05})
        out = apply_abstention_policy(r, CAT_SPEC, policy)
        assert out.accepted is True
        assert out.value == "a"

    def test_apply_policy_review_band(self):
        policy = DecisionPolicy(minimum_probability=0.5,
                                review_band=(0.5, 0.8))
        r = DecisionResult(value="a", probability=0.6,
                           distribution={"a": 0.6, "b": 0.2, "c": 0.2})
        out = apply_abstention_policy(r, CAT_SPEC, policy)
        assert out.accepted is False
        assert out.value == "a"
        assert out.metadata["policy_verdict"] == "review"

    def test_apply_policy_abstain_below_minimum(self):
        policy = DecisionPolicy(minimum_probability=0.5)
        r = DecisionResult(value="a", probability=0.3,
                           distribution={"a": 0.3, "b": 0.35, "c": 0.35})
        out = apply_abstention_policy(r, CAT_SPEC, policy)
        assert out.value is None
        assert out.accepted is False
        assert "below minimum" in out.metadata["abstain_reason"]

    def test_apply_policy_abstain_latency(self):
        policy = DecisionPolicy(maximum_latency_ms=10.0)
        r = DecisionResult(value="a", probability=0.9,
                           distribution={"a": 0.9, "b": 0.05, "c": 0.05},
                           latency_ms=50.0)
        out = apply_abstention_policy(r, CAT_SPEC, policy)
        assert out.value is None
        assert "latency" in out.metadata["abstain_reason"]


# --------------------------------------------------------------------------
# Slice 16 — thresholding
# --------------------------------------------------------------------------

class TestThresholding:
    def test_per_option_pass(self):
        config = ThresholdConfig(per_option={"a": 0.8})
        r = DecisionResult(value="a", probability=0.9,
                           distribution={"a": 0.9, "b": 0.05, "c": 0.05})
        out = apply_thresholds(r, CAT_SPEC, config)
        assert out.accepted is True
        assert out.metadata["thresholds_passed"] is True

    def test_per_option_fail_abstains(self):
        config = ThresholdConfig(per_option={"a": 0.95})
        r = DecisionResult(value="a", probability=0.9,
                           distribution={"a": 0.9, "b": 0.05, "c": 0.05})
        out = apply_thresholds(r, CAT_SPEC, config)
        assert out.value is None
        assert "per-option" in out.metadata["abstain_reason"]

    def test_per_option_ignores_other_options(self):
        config = ThresholdConfig(per_option={"a": 0.99})
        r = DecisionResult(value="b", probability=0.9,
                           distribution={"a": 0.05, "b": 0.9, "c": 0.05})
        out = apply_thresholds(r, CAT_SPEC, config)
        assert out.accepted is True

    def test_ordinal_cumulative_probability(self):
        r = DecisionResult(value="moderate", probability=0.5,
                           distribution={"low": 0.2, "moderate": 0.5,
                                         "high": 0.3})
        assert ordinal_cumulative_probability(r, ORD_SPEC, "moderate") == \
            pytest.approx(0.8)
        assert ordinal_cumulative_probability(r, ORD_SPEC, "high") == \
            pytest.approx(0.3)
        assert ordinal_cumulative_probability(r, ORD_SPEC, "low") == \
            pytest.approx(1.0)

    def test_ordinal_cumulative_pass_and_fail(self):
        config = ThresholdConfig(ordinal_minimum=("moderate", 0.75))
        good = DecisionResult(value="moderate", probability=0.5,
                              distribution={"low": 0.2, "moderate": 0.5,
                                            "high": 0.3})
        assert apply_thresholds(good, ORD_SPEC, config).accepted is True
        bad = DecisionResult(value="low", probability=0.6,
                             distribution={"low": 0.6, "moderate": 0.3,
                                           "high": 0.1})
        out = apply_thresholds(bad, ORD_SPEC, config)
        assert out.value is None
        assert "at least" in out.metadata["abstain_reason"]

    def test_ordinal_unknown_level_rejected(self):
        r = DecisionResult(value="low", probability=0.9,
                           distribution={"low": 0.9, "moderate": 0.05,
                                         "high": 0.05})
        with pytest.raises(PolicyError):
            ordinal_cumulative_probability(r, ORD_SPEC, "extreme")

    def test_numeric_band_classification(self):
        bands = [NumericBand("normal", 36.0, 37.5),
                 NumericBand("fever", 37.5, 42.0, min_probability=0.9)]
        assert classify_numeric_band(37.0, bands).name == "normal"
        assert classify_numeric_band(38.5, bands).name == "fever"
        assert classify_numeric_band(50.0, bands) is None

    def test_numeric_band_pass_and_fail(self):
        bands = [NumericBand("normal", 0.0, 37.5, min_probability=0.5),
                 NumericBand("fever", 37.5, 100.0, min_probability=0.9)]
        config = ThresholdConfig(numeric_bands=bands)
        ok = DecisionResult(value=38.5, probability=0.95)
        out = apply_thresholds(ok, NUM_SPEC, config)
        assert out.accepted is True
        assert out.metadata["numeric_band"] == "fever"
        weak = DecisionResult(value=38.5, probability=0.5)
        out2 = apply_thresholds(weak, NUM_SPEC, config)
        assert out2.value is None
        assert "fever" in out2.metadata["abstain_reason"]

    def test_numeric_value_in_no_band_abstains(self):
        config = ThresholdConfig(numeric_bands=[NumericBand("x", 0, 1)])
        r = DecisionResult(value=99.0, probability=0.99)
        out = apply_thresholds(r, NUM_SPEC, config)
        assert out.value is None
        assert "no defined band" in out.metadata["abstain_reason"]

    def test_policy_floor_applies(self):
        policy = DecisionPolicy(minimum_probability=0.8)
        r = DecisionResult(value="a", probability=0.7,
                           distribution={"a": 0.7, "b": 0.15, "c": 0.15})
        out = apply_thresholds(r, CAT_SPEC, ThresholdConfig(), policy)
        assert out.value is None

    def test_config_global_minimum_overrides_policy(self):
        policy = DecisionPolicy(minimum_probability=0.9)
        config = ThresholdConfig(global_minimum=0.5)
        r = DecisionResult(value="a", probability=0.7,
                           distribution={"a": 0.7, "b": 0.15, "c": 0.15})
        out = apply_thresholds(r, CAT_SPEC, config, policy)
        assert out.accepted is True

    def test_invalid_band_rejected(self):
        with pytest.raises(PolicyError):
            NumericBand("bad", lo=5.0, hi=1.0)


# --------------------------------------------------------------------------
# Slice 17 — health monitor
# --------------------------------------------------------------------------

class TestHealthMonitor:
    def test_unknown_backend_scores_one(self):
        m = HealthMonitor()
        assert m.score("ghost") == 1.0
        assert m.is_quarantined("ghost") is False

    def test_stats_percentiles_and_error_rate(self):
        m = HealthMonitor()
        for ms in [10, 20, 30, 40, 50]:
            m.record("b", ms, ok=True)
        m.record("b", 60, ok=False)
        s = m.stats("b")
        assert s["samples"] == 6
        assert s["error_rate"] == pytest.approx(1 / 6)
        assert s["p50_ms"] == pytest.approx(30.0)
        assert s["p99_ms"] == pytest.approx(60.0)
        assert s["consecutive_failures"] == 1

    def test_healthy_backend_not_quarantined(self):
        m = HealthMonitor()
        for _ in range(10):
            m.record("b", 50.0, ok=True)
        assert m.score("b") == pytest.approx(1.0)
        assert m.is_quarantined("b") is False

    def test_consecutive_failures_quarantine(self):
        m = HealthMonitor(max_consecutive_failures=3)
        for _ in range(3):
            m.record("b", 10.0, ok=False)
        assert m.is_quarantined("b") is True
        assert m.quarantined() == ["b"]

    def test_low_score_quarantine(self):
        m = HealthMonitor(quarantine_threshold=0.5)
        for _ in range(10):
            m.record("b", 10.0, ok=False)
        assert m.score("b") < 0.5
        assert m.is_quarantined("b") is True

    def test_auto_recover_on_success(self):
        m = HealthMonitor(max_consecutive_failures=2)
        m.record("b", 10.0, ok=False)
        m.record("b", 10.0, ok=False)
        assert m.is_quarantined("b") is True
        for _ in range(10):
            m.record("b", 10.0, ok=True)
        assert m.is_quarantined("b") is False
        assert m.quarantined() == []

    def test_latency_degrades_score(self):
        m = HealthMonitor(latency_target_ms=100.0)
        for _ in range(5):
            m.record("slowpoke", 400.0, ok=True)
        assert m.score("slowpoke") == pytest.approx(0.25)

    def test_reset(self):
        m = HealthMonitor(max_consecutive_failures=1)
        m.record("b", 1.0, ok=False)
        assert m.is_quarantined("b") is True
        m.reset("b")
        assert m.is_quarantined("b") is False
        assert m.score("b") == 1.0


# --------------------------------------------------------------------------
# Slice 18 — circuit breaker
# --------------------------------------------------------------------------

class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker("b", clock=FakeClock())
        assert cb.state == CLOSED
        assert cb.allow() is True

    def test_trips_after_threshold(self):
        clock = FakeClock()
        cb = CircuitBreaker("b", failure_threshold=3, clock=clock)
        for _ in range(2):
            cb.record_failure()
            assert cb.state == CLOSED
        cb.record_failure()
        assert cb.state == OPEN
        assert cb.allow() is False

    def test_half_open_after_timeout(self):
        clock = FakeClock()
        cb = CircuitBreaker("b", failure_threshold=1, reset_timeout_s=30.0,
                            clock=clock)
        cb.record_failure()
        assert cb.allow() is False
        clock.advance(29.0)
        assert cb.allow() is False
        clock.advance(2.0)
        assert cb.state == HALF_OPEN
        assert cb.allow() is True

    def test_probe_success_closes(self):
        clock = FakeClock()
        cb = CircuitBreaker("b", failure_threshold=1, reset_timeout_s=10.0,
                            clock=clock)
        cb.record_failure()
        clock.advance(11.0)
        assert cb.allow() is True  # the probe
        cb.record_success()
        assert cb.state == CLOSED
        assert cb.allow() is True

    def test_probe_failure_reopens(self):
        clock = FakeClock()
        cb = CircuitBreaker("b", failure_threshold=1, reset_timeout_s=10.0,
                            clock=clock)
        cb.record_failure()
        clock.advance(11.0)
        assert cb.allow() is True
        cb.record_failure()
        assert cb.state == OPEN
        assert cb.allow() is False

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker("b", failure_threshold=3, clock=FakeClock())
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CLOSED  # count restarted after the success

    def test_half_open_probe_limit(self):
        clock = FakeClock()
        cb = CircuitBreaker("b", failure_threshold=1, reset_timeout_s=10.0,
                            half_open_max_probes=1, clock=clock)
        cb.record_failure()
        clock.advance(11.0)
        assert cb.allow() is True
        assert cb.allow() is False  # probe slot consumed

    def test_registry_creates_and_configures(self):
        clock = FakeClock()
        reg = CircuitRegistry(clock=clock)
        a = reg.get("x")
        assert reg.get("x") is a
        reg.configure("y", failure_threshold=1)
        reg.get("y").record_failure()
        assert reg.get("y").state == OPEN
        snap = reg.snapshot()
        assert snap["x"]["state"] == CLOSED
        assert snap["y"]["state"] == OPEN

    def test_invalid_config_rejected(self):
        with pytest.raises(ValueError):
            CircuitBreaker("b", failure_threshold=0)


# --------------------------------------------------------------------------
# Slice 19 — timeouts
# --------------------------------------------------------------------------

class TestTimeouts:
    def test_fast_function_unaffected(self):
        assert run_with_deadline(lambda: 42, 1.0) == 42

    def test_slow_function_times_out(self):
        with pytest.raises(TimeoutError):
            run_with_deadline(lambda: time.sleep(0.5), 0.05)

    def test_function_exception_propagates(self):
        def boom():
            raise BackendError("inner")
        with pytest.raises(BackendError):
            run_with_deadline(boom, 1.0)

    def test_nonpositive_deadline_rejected(self):
        with pytest.raises(ValueError):
            run_with_deadline(lambda: 1, 0.0)

    def test_deadline_prefers_policy_cap(self):
        policy = DecisionPolicy(maximum_latency_ms=100.0)
        backend = SlowBackend(delay_s=1.0)  # estimate 1000ms * headroom
        assert deadline_ms_for(backend, policy, headroom=1.5) == 100.0

    def test_deadline_uses_estimate_times_headroom(self):
        backend = SlowBackend(delay_s=0.2)  # estimate 200ms
        assert deadline_ms_for(backend, None, headroom=2.0) == pytest.approx(400.0)

    def test_evaluate_with_timeout_fast_ok(self):
        result = evaluate_with_timeout(OkBackend("a"), {}, CAT_SPEC, 500.0)
        assert result.value == "a"

    def test_evaluate_with_timeout_slow_raises(self):
        with pytest.raises(TimeoutError):
            evaluate_with_timeout(SlowBackend(delay_s=0.3), {}, CAT_SPEC, 50.0)

    def test_timeout_backend_wrapper_marks_metadata(self):
        wrapped = TimeoutBackend(OkBackend("a"), explicit_deadline_ms=500.0)
        result = wrapped.evaluate({}, CAT_SPEC)
        assert result.value == "a"
        assert result.metadata["timeout_guarded"] is True
        assert result.metadata["deadline_ms"] == 500.0
        assert wrapped.name == "ok"  # attribution preserved

    def test_timeout_backend_wrapper_times_out(self):
        wrapped = TimeoutBackend(SlowBackend(delay_s=0.3),
                                 explicit_deadline_ms=50.0)
        with pytest.raises(TimeoutError):
            wrapped.evaluate({}, CAT_SPEC)


# --------------------------------------------------------------------------
# Slice 20 — deterministic reference runtime milestone
# --------------------------------------------------------------------------

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
sys.path.insert(0, str(EXAMPLES_DIR))
import event_triage


class TestMilestone:
    def test_escalate_critical_malware(self):
        gate = event_triage.build_gate()
        r = event_triage.triage(gate, {"severity": 9, "category": "malware"})
        assert r.value == "escalate"
        assert r.probability == pytest.approx(0.97)
        assert r.accepted is True
        assert r.fallback_used is True  # legacy scorer was offline

    def test_ignore_known_false_positive(self):
        gate = event_triage.build_gate()
        r = event_triage.triage(gate, {"severity": 1, "signature": "FP-HEARTBEAT"})
        assert r.value == "ignore"

    def test_dead_sensor_fails_over_to_rules(self):
        gate = event_triage.build_gate()
        r = event_triage.triage(
            gate, {"severity": 7, "category": "phishing", "sensor": "dead"})
        assert r.value == "inspect"
        assert r.fallback_used is True
        trace = r.metadata["fallback_trace"]
        assert trace[0]["backend"] == "legacy-scorer"
        assert trace[0]["outcome"] == "failed"
        assert trace[1]["backend"] == "security-event-triage"  # YAML name
        assert trace[1]["outcome"] == "ok"

    def test_default_rule_logs_unknown(self):
        gate = event_triage.build_gate()
        r = event_triage.triage(gate, {"severity": 4, "category": "auth"})
        assert r.value == "log"

    def test_provenance_records_decisions(self):
        gate = event_triage.build_gate()
        event_triage.triage(gate, {"severity": 9, "category": "malware"})
        event_triage.triage(
            gate, {"severity": 7, "category": "phishing", "sensor": "dead"})
        records = gate.provenance.recent(10)
        assert len(records) == 2
        assert records[0].value == "escalate"
        assert records[1].value == "inspect"
        assert records[1].fallback_used is True
        assert all(rec.request_hash for rec in records)

    def test_zero_ml_end_to_end(self):
        # The whole milestone runs with no ML stack: rules -> policy ->
        # fallback -> provenance, decided inside the spec's value space.
        gate = event_triage.build_gate()
        for event in event_triage.SAMPLE_EVENTS:
            r = event_triage.triage(gate, event)
            assert r.value in ("ignore", "log", "inspect", "escalate")
            assert r.accepted is True
