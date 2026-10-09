"""Slice 356 — Stratified evaluation.

Covers: per-stratum metrics, macro vs micro aggregation, worst-stratum
and disparity queries, missing-label refusal, key_fn strata, single
stratum, count summation, serialization round-trip.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionSpec
from hugrgate.errors import DatasetError
from hugrgate.evlab import StratifiedReport, stratified_evaluate


def _dataset():
    items = []
    for i in range(20):
        stratum = "easy" if i < 10 else "hard"
        expected = "a" if stratum == "easy" else "b"
        items.append({"state": {"x": i}, "expected": expected,
                      "stratum": stratum})
    return {
        "name": "strat-smoke",
        "version": "1.0.0",
        "spec": DecisionSpec(type="categorical",
                             options=["a", "b"]).to_dict(),
        "items": items,
    }


def test_per_stratum_metrics(gate_with_stub):
    report = stratified_evaluate(_dataset(), gate_with_stub,
                                 stratify_key="stratum",
                                 backends=["stub"])
    assert report.strata == ["easy", "hard"]
    assert report.stratum_sizes == {"easy": 10, "hard": 10}
    # stub always answers "a": perfect on easy, wrong on hard.
    assert report.per_stratum["easy"]["stub"]["accuracy"] == \
        pytest.approx(1.0)
    assert report.per_stratum["hard"]["stub"]["accuracy"] == \
        pytest.approx(0.0)


def test_macro_micro_aggregates(gate_with_stub):
    report = stratified_evaluate(_dataset(), gate_with_stub,
                                 stratify_key="stratum",
                                 backends=["stub"])
    agg = report.aggregate["stub"]["accuracy"]
    assert agg["macro"] == pytest.approx(0.5)
    assert agg["micro"] == pytest.approx(0.5)


def test_micro_weights_by_size(gate_with_stub):
    ds = _dataset()
    # 90 easy items, 10 hard: micro >> macro.
    extra = [{"state": {"x": 100 + i}, "expected": "a", "stratum": "easy"}
             for i in range(80)]
    ds["items"] = ds["items"] + extra
    report = stratified_evaluate(ds, gate_with_stub,
                                 stratify_key="stratum",
                                 backends=["stub"])
    agg = report.aggregate["stub"]["accuracy"]
    assert agg["macro"] == pytest.approx(0.5)
    assert agg["micro"] == pytest.approx(0.9)


def test_counts_sum_for_micro(gate_with_stub):
    report = stratified_evaluate(_dataset(), gate_with_stub,
                                 stratify_key="stratum",
                                 backends=["stub"])
    agg = report.aggregate["stub"]["n_decided"]
    assert agg["micro"] == pytest.approx(20.0)
    assert agg["macro"] == pytest.approx(10.0)


def test_worst_stratum(gate_with_stub):
    report = stratified_evaluate(_dataset(), gate_with_stub,
                                 stratify_key="stratum",
                                 backends=["stub"])
    assert report.worst_stratum("stub", "accuracy") == ("hard", 0.0)
    # lower-better: worst ece is the max.
    name, _ = report.worst_stratum("stub", "ece", higher_better=False)
    assert name == "hard"
    assert report.worst_stratum("stub", "nope") == (None, None)


def test_disparity(gate_with_stub):
    report = stratified_evaluate(_dataset(), gate_with_stub,
                                 stratify_key="stratum",
                                 backends=["stub"])
    assert report.disparity("stub", "accuracy") == pytest.approx(1.0)
    assert report.disparity("stub", "nope") is None


def test_missing_label_refused(gate_with_stub):
    ds = _dataset()
    del ds["items"][0]["stratum"]
    with pytest.raises(DatasetError):
        stratified_evaluate(ds, gate_with_stub, stratify_key="stratum")


def test_no_key_or_fn_rejected(gate_with_stub):
    with pytest.raises(DatasetError):
        stratified_evaluate(_dataset(), gate_with_stub)


def test_empty_items_rejected(gate_with_stub):
    ds = _dataset()
    ds["items"] = []
    with pytest.raises(DatasetError):
        stratified_evaluate(ds, gate_with_stub, stratify_key="stratum")


def test_key_fn_strata(gate_with_stub):
    report = stratified_evaluate(
        _dataset(), gate_with_stub,
        key_fn=lambda item: item["stratum"], backends=["stub"])
    assert report.stratify_key == "key_fn"
    assert report.strata == ["easy", "hard"]


def test_single_stratum(gate_with_stub):
    ds = _dataset()
    for item in ds["items"]:
        item["stratum"] = "only"
    report = stratified_evaluate(ds, gate_with_stub,
                                 stratify_key="stratum",
                                 backends=["stub"])
    agg = report.aggregate["stub"]["accuracy"]
    assert agg["macro"] == pytest.approx(0.5)
    assert agg["micro"] == pytest.approx(0.5)
    assert report.disparity("stub", "accuracy") is None


def test_report_roundtrip(gate_with_stub):
    report = stratified_evaluate(_dataset(), gate_with_stub,
                                 stratify_key="stratum",
                                 backends=["stub"])
    clone = StratifiedReport.from_dict(report.to_dict())
    assert clone.to_dict() == report.to_dict()
    assert clone.worst_stratum("stub", "accuracy") == ("hard", 0.0)


def test_max_items_truncates(gate_with_stub):
    report = stratified_evaluate(_dataset(), gate_with_stub,
                                 stratify_key="stratum",
                                 backends=["stub"], max_items=10)
    assert report.n_items == 10
    assert report.strata == ["easy"]
