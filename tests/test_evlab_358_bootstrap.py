"""Slice 358 — Bootstrap confidence intervals.

Covers: CI containment of the point estimate, width shrinking with
sample size, degenerate (all-correct) intervals, determinism,
builtin/custom/unknown metrics, argument validation, backend-level
CI end-to-end, abstention handling, and serialization round-trip.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionSpec
from hugrgate.backend import Backend
from hugrgate.errors import Abstention, EvalError
from hugrgate.evlab import (
    BootstrapCI,
    bootstrap_backend_ci,
    bootstrap_metric_ci,
)
from hugrgate.result import DecisionResult


def _pairs(n_correct, n_wrong, prob=0.8):
    pairs = []
    for _ in range(n_correct):
        pairs.append(("a", DecisionResult(
            value="a", probability=prob,
            distribution={"a": prob, "b": 1 - prob})))
    for _ in range(n_wrong):
        pairs.append(("a", DecisionResult(
            value="b", probability=prob,
            distribution={"a": 1 - prob, "b": prob})))
    return pairs


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def test_ci_contains_estimate():
    ci = bootstrap_metric_ci(_pairs(70, 30), _spec(), "accuracy",
                             n_boot=500, seed=1)
    assert ci.estimate == pytest.approx(0.7)
    assert ci.ci_low <= ci.estimate <= ci.ci_high
    assert ci.contains(0.7)
    assert not ci.contains(0.99)
    assert ci.width > 0
    assert ci.n_items == 100
    assert ci.ci_level == 0.95


def test_width_shrinks_with_sample_size():
    small = bootstrap_metric_ci(_pairs(35, 15), _spec(), "accuracy",
                                n_boot=500, seed=2)
    large = bootstrap_metric_ci(_pairs(350, 150), _spec(), "accuracy",
                                n_boot=500, seed=2)
    assert large.width < small.width


def test_degenerate_all_correct():
    ci = bootstrap_metric_ci(_pairs(50, 0), _spec(), "accuracy",
                             n_boot=500, seed=3)
    assert ci.estimate == pytest.approx(1.0)
    assert ci.ci_low == pytest.approx(1.0)
    assert ci.ci_high == pytest.approx(1.0)
    assert ci.width == pytest.approx(0.0)


def test_deterministic():
    kw = dict(n_boot=500, seed=9)
    c1 = bootstrap_metric_ci(_pairs(60, 40), _spec(), "accuracy", **kw)
    c2 = bootstrap_metric_ci(_pairs(60, 40), _spec(), "accuracy", **kw)
    assert c1.to_dict() == c2.to_dict()
    c3 = bootstrap_metric_ci(_pairs(60, 40), _spec(), "accuracy",
                             n_boot=500, seed=10)
    assert (c1.ci_low, c1.ci_high) != (c3.ci_low, c3.ci_high)


def test_builtin_metrics():
    pairs = _pairs(60, 40)
    for name in ("accuracy", "brier_score", "ece"):
        ci = bootstrap_metric_ci(pairs, _spec(), name,
                                 n_boot=300, seed=4)
        assert ci.metric == name
        assert ci.contains(ci.estimate)


def test_custom_metric_callable():
    def error_rate(pairs, spec):
        acc = sum(1 for e, r in pairs if r.value == e) / len(pairs)
        return 1.0 - acc

    ci = bootstrap_metric_ci(_pairs(70, 30), _spec(), error_rate,
                             n_boot=300, seed=5)
    assert ci.metric == "error_rate"
    assert ci.estimate == pytest.approx(0.3)


def test_unknown_metric_rejected():
    with pytest.raises(EvalError):
        bootstrap_metric_ci(_pairs(10, 10), _spec(), "f1",
                            n_boot=100)


def test_argument_validation():
    pairs, spec = _pairs(10, 10), _spec()
    with pytest.raises(EvalError):
        bootstrap_metric_ci(pairs, spec, n_boot=50)  # too few
    with pytest.raises(EvalError):
        bootstrap_metric_ci(pairs, spec, ci=1.5)
    with pytest.raises(EvalError):
        bootstrap_metric_ci(pairs, spec, ci=0.0)
    with pytest.raises(EvalError):
        bootstrap_metric_ci(_pairs(1, 0), spec)  # single item


def test_abstentions_skipped():
    pairs = [*_pairs(40, 10), ("a", None), ("b", None)]
    ci = bootstrap_metric_ci(pairs, _spec(), "accuracy",
                             n_boot=300, seed=6)
    assert ci.n_items == 50
    assert ci.estimate == pytest.approx(0.8)


def test_metric_undefined_on_resamples_rejected():
    # A metric that is None on every resample -> honest failure.
    def never(pairs, spec):
        return None

    with pytest.raises(EvalError):
        bootstrap_metric_ci(_pairs(20, 20), _spec(), never,
                            n_boot=100, seed=7)


def test_roundtrip():
    ci = bootstrap_metric_ci(_pairs(60, 40), _spec(), "accuracy",
                             n_boot=300, seed=8)
    assert BootstrapCI.from_dict(ci.to_dict()).to_dict() == ci.to_dict()


# --- backend-level ---------------------------------------------------------------

def _dataset(n=60):
    return {
        "name": "boot-smoke",
        "version": "1.0.0",
        "spec": DecisionSpec(type="categorical",
                             options=["a", "b"]).to_dict(),
        "items": [{"state": {"x": i},
                   "expected": "a" if i % 4 else "b"}
                  for i in range(n)],
    }


def test_bootstrap_backend_ci_end_to_end(gate_with_stub):
    ci = bootstrap_backend_ci(_dataset(), gate_with_stub, "stub",
                              "accuracy", n_boot=500, seed=21)
    # stub answers "a": 45/60 correct.
    assert ci.estimate == pytest.approx(0.75)
    assert ci.contains(0.75)
    assert ci.width > 0


def test_bootstrap_backend_ci_with_abstaining_backend(gate_with_stub):
    class SometimesAbstains(Backend):
        name = "sometimes"

        def capabilities(self):
            return {"spec_types": ["categorical"]}

        def supports(self, spec):
            return spec.type == "categorical"

        def evaluate(self, state, spec, context=None):
            if state["x"] % 2 == 0:
                raise Abstention("nope")
            return DecisionResult(value="a", probability=0.9,
                                  distribution={"a": 0.9, "b": 0.1})

    gate_with_stub.register(SometimesAbstains())
    ci = bootstrap_backend_ci(_dataset(40), gate_with_stub, "sometimes",
                              "accuracy", n_boot=300, seed=22)
    assert ci.n_items == 20  # half abstained
    assert ci.contains(ci.estimate)
