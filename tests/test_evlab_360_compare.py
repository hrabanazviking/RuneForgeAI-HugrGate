"""Slice 360 — Paired backend comparisons.

Covers: a_better/b_better verdicts with significant diffs, tie for
identical backends, win/tie/loss accounting, bootstrap diff-CI
placement, brier_score comparisons, unsupported-metric and
self-comparison rejection, joint-scoring requirement, and
serialization round-trip.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionSpec
from hugrgate.backend import Backend
from hugrgate.errors import EvalError
from hugrgate.evlab import BackendComparison, compare_backends
from hugrgate.result import DecisionResult as DR


class FixedBackend(Backend):
    """Answers a fixed value with a fixed confidence."""

    def __init__(self, name, value, prob=0.9):
        self.name = name
        self.value = value
        self.prob = prob

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        options = spec.options or ["a", "b"]
        rest = (1.0 - self.prob) / max(len(options) - 1, 1)
        dist = {o: (self.prob if o == self.value else rest)
                for o in options}
        return DR(value=self.value, probability=self.prob,
                  distribution=dist)


def _dataset(n=60):
    return {
        "name": "cmp-smoke",
        "version": "1.0.0",
        "spec": DecisionSpec(type="categorical",
                             options=["a", "b"]).to_dict(),
        "items": [{"state": {"x": i},
                   "expected": "a" if i % 4 else "b"}
                  for i in range(n)],
    }


@pytest.fixture
def two_backends(gate_with_stub):
    gate_with_stub.register(FixedBackend("good", "a", prob=0.9))
    gate_with_stub.register(FixedBackend("bad", "b", prob=0.9))
    return gate_with_stub


def test_a_better_verdict(two_backends):
    comp = compare_backends(_dataset(), two_backends, "good", "bad",
                            n_boot=500, n_perm=2000, seed=3)
    # good answers "a" (45/60 right); bad answers "b" (15/60 right).
    assert comp.estimate_a == pytest.approx(0.75)
    assert comp.estimate_b == pytest.approx(0.25)
    assert comp.mean_diff == pytest.approx(0.5)
    assert comp.significant
    assert comp.verdict == "a_better"
    assert comp.diff_ci_low > 0  # CI excludes zero
    assert comp.wins_a == 45
    assert comp.wins_b == 15
    assert comp.ties == 0
    assert comp.n_joint == 60


def test_b_better_verdict(two_backends):
    comp = compare_backends(_dataset(), two_backends, "bad", "good",
                            n_boot=500, n_perm=2000, seed=3)
    assert comp.verdict == "b_better"
    assert comp.mean_diff == pytest.approx(-0.5)


def test_tie_for_identical(two_backends):
    # A true clone: identical behavior -> tie.
    two_backends.register(FixedBackend("good-clone", "a", prob=0.9))
    comp = compare_backends(_dataset(), two_backends, "good", "good-clone",
                            n_boot=500, n_perm=2000, seed=3)
    assert comp.mean_diff == pytest.approx(0.0)
    assert not comp.significant
    assert comp.verdict == "tie"
    assert comp.ties == 60
    assert comp.p_value == pytest.approx(1.0)


def test_brier_score_comparison(two_backends):
    comp = compare_backends(_dataset(), two_backends, "good", "bad",
                            metric="brier_score",
                            n_boot=500, n_perm=2000, seed=5)
    assert comp.higher_better is False
    # good's per-item squared error is lower on average.
    assert comp.mean_diff < 0
    assert comp.verdict == "a_better"
    assert comp.estimate_a < comp.estimate_b


def test_unsupported_metric_rejected(two_backends):
    with pytest.raises(EvalError):
        compare_backends(_dataset(), two_backends, "good", "bad",
                         metric="ece")


def test_self_comparison_rejected(two_backends):
    with pytest.raises(EvalError):
        compare_backends(_dataset(), two_backends, "good", "good")


def test_needs_jointly_scored_items(gate_with_stub):
    from hugrgate.errors import Abstention

    class AlwaysAbstains(Backend):
        name = "abstainer"

        def capabilities(self):
            return {"spec_types": ["categorical"]}

        def supports(self, spec):
            return spec.type == "categorical"

        def evaluate(self, state, spec, context=None):
            raise Abstention("nope")

    gate_with_stub.register(AlwaysAbstains())
    with pytest.raises(EvalError):
        compare_backends(_dataset(10), gate_with_stub, "stub", "abstainer")


def test_comparison_roundtrip(two_backends):
    comp = compare_backends(_dataset(), two_backends, "good", "bad",
                            n_boot=500, n_perm=2000, seed=3)
    clone = BackendComparison.from_dict(comp.to_dict())
    assert clone.to_dict() == comp.to_dict()
    assert clone.verdict == "a_better"


def test_max_items_respected(two_backends):
    comp = compare_backends(_dataset(60), two_backends, "good", "bad",
                            n_boot=300, n_perm=1000, seed=3,
                            max_items=20)
    assert comp.n_items == 20
    assert comp.n_joint == 20
