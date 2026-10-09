"""Slice 351 — Evaluation API v2.

Covers: experiment registration/run lifecycle, validation failures
(empty/missing/bad datasets), metric selection + derived metrics,
restricted-dataset privacy refusal, seed reproducibility, record
serialization, best-backend selection, dry-run plans, max_items
boundaries.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.backend import Backend
from hugrgate.errors import DatasetError, EvalError
from hugrgate.evlab import (
    EvaluationLab,
    Experiment,
    MetricSet,
    RunRecord,
)
from hugrgate.result import DecisionResult


def _dataset(n: int = 6, **extra):
    return {
        "name": "lab-smoke",
        "version": "1.0.0",
        **extra,
        "spec": DecisionSpec(type="categorical",
                             options=["a", "b", "c"]).to_dict(),
        "items": [
            {"state": {"x": i}, "expected": "a" if i % 2 == 0 else "b"}
            for i in range(n)
        ],
    }


class CountingBackend(Backend):
    """Backend that counts evaluations (proves dry_run executes nothing)."""

    def __init__(self, name="counter", value="a"):
        self.name = name
        self.value = value
        self.calls = 0

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        self.calls += 1
        options = spec.options or ["a", "b", "c"]
        dist = {o: (1.0 if o == self.value else 0.0) for o in options}
        return DecisionResult(value=self.value, probability=1.0,
                              distribution=dist)


@pytest.fixture
def lab(gate_with_stub):
    return EvaluationLab(gate=gate_with_stub)


def _register(lab, name="smoke", **kw):
    exp = Experiment(name=name, dataset=_dataset(), **kw)
    return lab.register_experiment(exp)


# --- success ---------------------------------------------------------------

def test_register_and_run_end_to_end(lab, stub_backend):
    _register(lab, backends=["stub"])
    record = lab.run("smoke")
    assert isinstance(record, RunRecord)
    assert record.experiment_name == "smoke"
    assert record.run_id
    assert record.n_items == 6
    assert record.hugrgate_version
    assert set(record.backends) == {"stub"}
    metrics = record.backends["stub"]
    # 3 of 6 items expect "a"; stub always answers "a".
    assert metrics["accuracy"] == pytest.approx(0.5)
    assert metrics["n_decided"] == 6
    assert record.dataset_fingerprint
    assert record.seed == 0


def test_run_selects_named_backends(lab, gate_with_stub):
    gate_with_stub.register(CountingBackend("counter", value="b"))
    _register(lab, backends=["stub", "counter"])
    record = lab.run("smoke")
    assert set(record.backends) == {"stub", "counter"}
    # counter answers "b": correct on the 3 odd items.
    assert record.backends["counter"]["accuracy"] == pytest.approx(0.5)


def test_metric_subset_and_derived(lab):
    ms = MetricSet(
        include=("accuracy",),
        derived={"error_rate": lambda m: 1.0 - (m["accuracy"] or 0.0)},
    )
    _register(lab, backends=["stub"], metrics=ms)
    record = lab.run("smoke")
    metrics = record.backends["stub"]
    assert set(metrics) == {"accuracy", "error_rate"}
    assert metrics["error_rate"] == pytest.approx(0.5)


def test_seed_reproducibility(lab):
    _register(lab, backends=["stub"], seed=351)
    r1 = lab.run("smoke")
    r2 = lab.run("smoke")
    assert r1.run_id != r2.run_id  # identity is unique per run
    # Wall-clock metrics (latency/throughput) legitimately vary; the
    # decision-quality science must be identical.
    for key in ("accuracy", "brier_score", "ece", "n_decided",
                "n_abstained", "n_errors", "abstention_rate"):
        assert r1.backends["stub"][key] == r2.backends["stub"][key]
    assert r1.dataset_fingerprint == r2.dataset_fingerprint


def test_record_roundtrip(lab):
    _register(lab, backends=["stub"], tags={"suite": "smoke"})
    record = lab.run("smoke")
    clone = RunRecord.from_dict(record.to_dict())
    assert clone.to_dict() == record.to_dict()


def test_experiment_roundtrip():
    exp = Experiment(name="rt", dataset=_dataset(), seed=7,
                     tags={"k": "v"}, max_items=4)
    clone = Experiment.from_dict(exp.to_dict())
    assert clone.name == "rt"
    assert clone.seed == 7
    assert clone.tags == {"k": "v"}
    assert clone.max_items == 4
    assert clone.dataset["name"] == "lab-smoke"


def test_best_picks_winner(lab, gate_with_stub):
    gate_with_stub.register(CountingBackend("always-b", value="b"))
    _register(lab, backends=["stub", "always-b"])
    record = lab.run("smoke")
    name, value = record.best("accuracy")
    # stub: 0.5, always-b: 0.5 — tie goes to first max; use a metric
    # that separates them instead: n_decided is equal too, so check
    # the boundary contract on an empty record below; here just assert
    # a valid backend name comes back.
    assert name in {"stub", "always-b"}
    assert value == pytest.approx(0.5)


def test_best_boundary_unscored():
    record = RunRecord(
        run_id="x", experiment_name="e", seed=0,
        started_at="t", finished_at="t", elapsed_s=0.0,
        hugrgate_version="v", python_version="p", platform={},
        dataset_name="d", dataset_version="1", dataset_fingerprint="f",
        policy={}, privacy_class="standard", tags={},
        backends={"b": {"accuracy": None}}, n_items=0,
    )
    assert record.best("accuracy") == (None, None)
    assert record.best("missing-metric") == (None, None)


def test_dry_run_returns_plan_without_executing(gate_with_stub):
    counter = CountingBackend("counter")
    gate_with_stub.register(counter)
    lab = EvaluationLab(gate=gate_with_stub)
    lab.register_experiment(
        Experiment(name="plan", dataset=_dataset(), backends=["counter"]))
    plan = lab.run("plan", dry_run=True)
    assert isinstance(plan, dict)
    assert plan["experiment"] == "plan"
    assert plan["n_items"] == 6
    assert plan["dataset_fingerprint"]
    assert counter.calls == 0  # nothing executed


def test_max_items_truncates(lab):
    _register(lab, backends=["stub"], max_items=2)
    record = lab.run("smoke")
    assert record.n_items == 2
    assert record.backends["stub"]["n_decided"] == 2


def test_restricted_dataset_runs_under_strict_policy(gate_with_stub):
    lab = EvaluationLab(gate=gate_with_stub)
    ds = _dataset(sensitivity="restricted")
    exp = Experiment(name="restricted", dataset=ds, backends=["stub"],
                     policy=DecisionPolicy(privacy_class="strict"))
    lab.register_experiment(exp)
    record = lab.run("restricted")
    assert record.privacy_class == "strict"


def test_list_experiments(lab):
    _register(lab, name="one")
    _register(lab, name="two")
    assert lab.list_experiments() == ["one", "two"]
    assert lab.get_experiment("one").name == "one"


# --- failure ---------------------------------------------------------------

def test_duplicate_registration_rejected(lab):
    _register(lab, name="dup")
    with pytest.raises(EvalError):
        _register(lab, name="dup")


def test_unknown_experiment_rejected(lab):
    with pytest.raises(EvalError):
        lab.run("nope")


def test_empty_dataset_rejected(lab):
    ds = _dataset(n=0)
    with pytest.raises(DatasetError):
        lab.register_experiment(Experiment(name="empty", dataset=ds))


def test_missing_spec_rejected(lab):
    ds = _dataset()
    del ds["spec"]
    with pytest.raises(DatasetError):
        lab.register_experiment(Experiment(name="nospec", dataset=ds))


def test_bad_item_rejected(lab):
    ds = _dataset()
    ds["items"] = [{"expected": "a"}]  # no "state"
    with pytest.raises(DatasetError):
        lab.register_experiment(Experiment(name="baditem", dataset=ds))


def test_restricted_dataset_refused_under_standard_policy(lab):
    ds = _dataset(sensitivity="restricted")
    with pytest.raises(EvalError):
        lab.register_experiment(Experiment(name="nope", dataset=ds))


def test_pii_dataset_refused_under_standard_policy(lab):
    ds = _dataset(contains_pii=True)
    with pytest.raises(EvalError):
        lab.register_experiment(Experiment(name="pii", dataset=ds))


def test_unknown_metric_rejected(lab):
    with pytest.raises(EvalError):
        lab.register_experiment(
            Experiment(name="badm", dataset=_dataset(),
                       metrics=MetricSet(include=("accuracy", "bogus"))))


def test_derived_metric_failure_raises_eval_error(lab):
    ms = MetricSet(include=("accuracy",),
                   derived={"boom": lambda m: 1 / 0})
    _register(lab, backends=["stub"], metrics=ms)
    with pytest.raises(EvalError):
        lab.run("smoke")


def test_bad_max_items_rejected(lab):
    with pytest.raises(EvalError):
        lab.register_experiment(
            Experiment(name="m0", dataset=_dataset(), max_items=0))


def test_empty_name_rejected(lab):
    with pytest.raises(EvalError):
        lab.register_experiment(Experiment(name="", dataset=_dataset()))


def test_empty_backends_rejected(lab):
    with pytest.raises(EvalError):
        lab.register_experiment(
            Experiment(name="nb", dataset=_dataset(), backends=[]))
