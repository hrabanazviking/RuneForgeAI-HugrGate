"""Slice 357 — Cross-validation harness.

Covers: fold geometry (sizes, coverage), per-fold metrics, aggregate
mean/std/min/max correctness, determinism, summarize/rank queries,
error paths (k bounds, empty items, unknown summarize), and
serialization round-trip.
"""

from __future__ import annotations

import statistics

import pytest

from hugrgate import DecisionSpec
from hugrgate.errors import DatasetError, EvalError
from hugrgate.evlab import CVReport, cross_validate


def _dataset(n=20):
    return {
        "name": "cv-smoke",
        "version": "1.0.0",
        "spec": DecisionSpec(type="categorical",
                             options=["a", "b"]).to_dict(),
        # Alternating expected values: fold accuracies vary honestly.
        "items": [{"state": {"x": i},
                   "expected": "a" if i % 3 else "b"}
                  for i in range(n)],
    }


def test_fold_geometry(gate_with_stub):
    report = cross_validate(_dataset(20), gate_with_stub, k=5, seed=7,
                            backends=["stub"])
    assert report.k == 5
    assert len(report.folds) == 5
    for fold in report.folds:
        assert fold.n_test == 4
        assert fold.n_train == 16
    tested = sum(f.n_test for f in report.folds)
    assert tested == 20


def test_per_fold_metrics_vary_honestly(gate_with_stub):
    # stub answers "a": folds with more "b"-expected items score lower.
    report = cross_validate(_dataset(20), gate_with_stub, k=5, seed=7,
                            backends=["stub"])
    accs = [f.backends["stub"]["accuracy"] for f in report.folds]
    assert len(set(accs)) > 1  # genuinely different folds
    agg = report.aggregate["stub"]["accuracy"]
    assert agg["mean"] == pytest.approx(statistics.fmean(accs))
    assert agg["std"] == pytest.approx(statistics.stdev(accs))
    assert agg["min"] == pytest.approx(min(accs))
    assert agg["max"] == pytest.approx(max(accs))
    assert agg["n_folds"] == 5.0


def test_deterministic(gate_with_stub):
    from hugrgate.evlab import MetricSet
    # Wall-clock metrics (latency/throughput) legitimately vary; the
    # decision-quality science must be identical for a fixed seed.
    quality = MetricSet(include=("accuracy", "brier_score", "ece",
                                 "n_decided", "n_abstained", "n_errors",
                                 "abstention_rate"))
    r1 = cross_validate(_dataset(20), gate_with_stub, k=4, seed=11,
                        backends=["stub"], metrics=quality)
    r2 = cross_validate(_dataset(20), gate_with_stub, k=4, seed=11,
                        backends=["stub"], metrics=quality)
    assert r1.to_dict() == r2.to_dict()
    r3 = cross_validate(_dataset(20), gate_with_stub, k=4, seed=12,
                        backends=["stub"], metrics=quality)
    assert r1.to_dict() != r3.to_dict()


def test_summarize(gate_with_stub):
    report = cross_validate(_dataset(20), gate_with_stub, k=5, seed=7,
                            backends=["stub"])
    summary = report.summarize("stub", "accuracy")
    assert set(summary) == {"mean", "std", "min", "max", "n_folds"}
    with pytest.raises(EvalError):
        report.summarize("ghost", "accuracy")
    with pytest.raises(EvalError):
        report.summarize("stub", "bogus")


def test_rank(gate_with_stub):
    from hugrgate.backend import Backend
    from hugrgate.result import DecisionResult

    class AlwaysB(Backend):
        name = "always-b"

        def capabilities(self):
            return {"spec_types": ["categorical"]}

        def supports(self, spec):
            return spec.type == "categorical"

        def evaluate(self, state, spec, context=None):
            return DecisionResult(value="b", probability=1.0,
                                  distribution={"a": 0.0, "b": 1.0})

    gate_with_stub.register(AlwaysB())
    report = cross_validate(_dataset(30), gate_with_stub, k=3, seed=5,
                            backends=["stub", "always-b"])
    ranking = report.rank("accuracy")
    assert [name for name, _ in ranking] == ["stub", "always-b"]
    # lower-better flips the order: stub's brier is 0-ish... both are
    # deterministic; just assert the rank call works and is stable.
    assert report.rank("accuracy", higher_better=False)[0][0] == "always-b"


def test_k_bounds(gate_with_stub):
    with pytest.raises(DatasetError):
        cross_validate(_dataset(10), gate_with_stub, k=1)
    with pytest.raises(DatasetError):
        cross_validate(_dataset(4), gate_with_stub, k=5)
    # k == n is leave-one-out.
    report = cross_validate(_dataset(6), gate_with_stub, k=6,
                            backends=["stub"])
    assert len(report.folds) == 6
    assert all(f.n_test == 1 for f in report.folds)


def test_empty_items_rejected(gate_with_stub):
    ds = _dataset(10)
    ds["items"] = []
    with pytest.raises(EvalError):
        cross_validate(ds, gate_with_stub)


def test_report_roundtrip(gate_with_stub):
    report = cross_validate(_dataset(20), gate_with_stub, k=4, seed=3,
                            backends=["stub"])
    clone = CVReport.from_dict(report.to_dict())
    assert clone.to_dict() == report.to_dict()
    assert clone.summarize("stub", "accuracy") == \
        report.summarize("stub", "accuracy")


def test_std_zero_for_identical_folds(gate_with_stub):
    ds = _dataset(20)
    for item in ds["items"]:
        item["expected"] = "a"  # stub is perfect everywhere
    report = cross_validate(ds, gate_with_stub, k=5, seed=7,
                            backends=["stub"])
    agg = report.aggregate["stub"]["accuracy"]
    assert agg["mean"] == pytest.approx(1.0)
    assert agg["std"] == pytest.approx(0.0)
