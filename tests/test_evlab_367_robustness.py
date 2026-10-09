"""Slice 367 — Robustness evaluation.

Covers: label-noise degradation shape (p=0 identical, p=1
predictable), binary label flips, state-dropout keep-one-key rule,
perturbation determinism and input immutability, p validation,
unsupported-spec rejection, robustness_score = min retention,
most_robust/fragile queries, and serialization round-trip.
"""

from __future__ import annotations

import random

import pytest

from hugrgate import DecisionSpec
from hugrgate.errors import EvalError
from hugrgate.evlab import (
    LabelNoise,
    RobustnessReport,
    StateDropout,
    robustness_evaluate,
)


def _dataset(n=60):
    return {
        "name": "robust-smoke",
        "version": "1.0.0",
        "spec": DecisionSpec(type="categorical",
                             options=["a", "b"]).to_dict(),
        "items": [{"state": {"x": i, "y": i * 2}, "expected": "a"}
                  for i in range(n)],
    }


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


# --- perturbations --------------------------------------------------------------------

def test_label_noise_p_zero_is_identity():
    items = [dict(i) for i in _dataset(20)["items"]]
    out = LabelNoise(0.0).apply(items, _spec(), random.Random(1))
    assert out == items


def test_label_noise_p_one_flips_everything():
    items = [dict(i) for i in _dataset(20)["items"]]
    out = LabelNoise(1.0).apply(items, _spec(), random.Random(1))
    assert all(row["expected"] == "b" for row in out)
    assert all(row["expected"] == "a" for row in items)  # inputs untouched


def test_label_noise_binary():
    spec = DecisionSpec(type="binary", statement="s?")
    items = [{"state": {}, "expected": True} for _ in range(10)]
    out = LabelNoise(1.0).apply(items, spec, random.Random(2))
    assert all(row["expected"] is False for row in out)


def test_label_noise_bad_spec_rejected():
    spec = DecisionSpec(type="numeric", minimum=0.0, maximum=1.0)
    with pytest.raises(EvalError):
        LabelNoise(0.5).apply([{"state": {}}], spec, random.Random(1))


def test_label_noise_p_validation():
    with pytest.raises(EvalError):
        LabelNoise(1.5)
    with pytest.raises(EvalError):
        StateDropout(-0.1)


def test_state_dropout_keeps_one_key():
    items = [{"state": {"a": 1, "b": 2, "c": 3}} for _ in range(30)]
    out = StateDropout(1.0).apply(items, _spec(), random.Random(3))
    assert all(len(row["state"]) == 1 for row in out)
    assert all(len(row["state"]) == 3 for row in items)  # untouched


def test_state_dropout_p_zero_is_identity():
    items = [dict(i) for i in _dataset(10)["items"]]
    out = StateDropout(0.0).apply(items, _spec(), random.Random(4))
    assert out == items


def test_perturbation_deterministic():
    items = [dict(i) for i in _dataset(30)["items"]]
    a = LabelNoise(0.3).apply(items, _spec(), random.Random(9))
    b = LabelNoise(0.3).apply(items, _spec(), random.Random(9))
    assert a == b


# --- evaluation --------------------------------------------------------------------------

def test_robustness_report_shape(gate_with_stub):
    report = robustness_evaluate(
        _dataset(), gate_with_stub, ["stub"],
        [LabelNoise(0.2), StateDropout(0.5)], seed=5)
    info = report.backends["stub"]
    assert info["baseline_accuracy"] == pytest.approx(1.0)
    assert set(info["perturbations"]) == {"label_noise(p=0.2)",
                                          "state_dropout(p=0.5)"}
    # stub ignores state: dropout retention is 1.0.
    assert info["perturbations"]["state_dropout(p=0.5)"][
        "retention"] == pytest.approx(1.0)
    # label noise at p=0.2 on all-"a" labels: ~80% stay "a".
    noisy_acc = info["perturbations"]["label_noise(p=0.2)"]["accuracy"]
    assert 0.7 < noisy_acc < 0.9
    assert info["robustness_score"] == pytest.approx(
        min(d["retention"] for d in info["perturbations"].values()))
    assert report.seed == 5


def test_robustness_deterministic(gate_with_stub):
    kw = dict(perturbations=[LabelNoise(0.3)], seed=8)
    r1 = robustness_evaluate(_dataset(30), gate_with_stub, ["stub"], **kw)
    r2 = robustness_evaluate(_dataset(30), gate_with_stub, ["stub"], **kw)
    assert r1.to_dict() == r2.to_dict()


def test_most_robust_and_fragile(gate_with_stub):
    from tests.conftest import StubBackend
    # wrong-stub answers "b" always: baseline 0 -> retention undefined.
    gate_with_stub.register(StubBackend(name="wrong", value="b"))
    report = robustness_evaluate(
        _dataset(), gate_with_stub, ["stub", "wrong"],
        [LabelNoise(0.5)], seed=5)
    name, score = report.most_robust()
    assert name == "stub"
    assert score == pytest.approx(
        report.backends["stub"]["robustness_score"])
    # wrong's baseline is 0: retention is undefined, not fabricated.
    assert report.backends["wrong"]["robustness_score"] is None
    fragile = report.fragile(threshold=0.8)
    assert [b for b, _ in fragile] == ["stub"]
    with pytest.raises(EvalError):
        report.fragile(threshold=2.0)


def test_default_perturbations(gate_with_stub):
    report = robustness_evaluate(_dataset(20), gate_with_stub, ["stub"])
    assert report.perturbations == ["label_noise(p=0.1)",
                                    "state_dropout(p=0.3)"]


def test_empty_items_rejected(gate_with_stub):
    ds = _dataset(5)
    ds["items"] = []
    with pytest.raises(EvalError):
        robustness_evaluate(ds, gate_with_stub, ["stub"])


def test_report_roundtrip(gate_with_stub):
    report = robustness_evaluate(_dataset(20), gate_with_stub, ["stub"],
                                 [LabelNoise(0.1)], seed=1)
    clone = RobustnessReport.from_dict(report.to_dict())
    assert clone.to_dict() == report.to_dict()
    assert clone.most_robust()[0] == "stub"
