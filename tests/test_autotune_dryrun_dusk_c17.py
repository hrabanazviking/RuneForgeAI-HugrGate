"""Slice 17 (Sif's Loom dusk Wave C) — autotune dry-run mode.

: meth:`ConfigStore.dry_run` runs the exact same validation/coercion as
:meth:`ConfigStore.apply` and reports what *would* change
(old -> new values) without mutating the parameter store.
"""

from __future__ import annotations

import pytest

from hugrgate.autotune.controller import ConfigStore, TunableParameter
from hugrgate.errors import ParameterError


def _stub_store() -> ConfigStore:
    store = ConfigStore()
    store.register(TunableParameter(
        name="learning_rate", dtype="float", default=0.01,
        lo=0.0001, hi=1.0, description="step size"))
    store.register(TunableParameter(
        name="batch_size", dtype="int", default=32,
        lo=1, hi=512, description="mini-batch size"))
    store.register(TunableParameter(
        name="use_fp16", dtype="bool", default=False,
        description="half precision"))
    store.register(TunableParameter(
        name="schedule", dtype="str", default="cosine",
        choices=("cosine", "linear", "constant"),
        description="lr schedule"))
    return store


def test_dry_run_report_is_non_empty_with_old_new_values():
    store = _stub_store()
    report = store.dry_run({"learning_rate": 0.05,
                            "batch_size": 128,
                            "use_fp16": True})
    assert report["mutated"] is False
    assert report["change_count"] == 3
    would_change = report["would_change"]
    assert would_change["learning_rate"] == {"old": 0.01, "new": 0.05}
    assert would_change["batch_size"] == {"old": 32, "new": 128}
    assert would_change["use_fp16"] == {"old": False, "new": True}


def test_dry_run_leaves_store_byte_identical():
    store = _stub_store()
    before = store.snapshot()
    report = store.dry_run({"learning_rate": 0.05, "schedule": "linear"})
    assert report["change_count"] == 2
    after = store.snapshot()
    assert after == before
    # Individual reads agree too.
    assert store.get("learning_rate") == 0.01
    assert store.get("schedule") == "cosine"


def test_dry_run_repeated_runs_never_mutate():
    store = _stub_store()
    for lr in (0.02, 0.03, 0.5):
        rep = store.dry_run({"learning_rate": lr})
        assert rep["would_change"]["learning_rate"]["new"] == float(lr)
        assert store.get("learning_rate") == 0.01
    assert store.snapshot() == {
        "learning_rate": 0.01, "batch_size": 32,
        "use_fp16": False, "schedule": "cosine"}


def test_dry_run_no_change_parameters_are_omitted():
    store = _stub_store()
    report = store.dry_run({"learning_rate": 0.01, "batch_size": 64})
    assert report["change_count"] == 1
    assert report["would_change"] == {"batch_size": {"old": 32, "new": 64}}


def test_dry_run_empty_changes_reports_nothing_and_mutates_nothing():
    store = _stub_store()
    before = store.snapshot()
    report = store.dry_run({})
    assert report["would_change"] == {}
    assert report["change_count"] == 0
    assert report["mutated"] is False
    assert store.snapshot() == before


def test_dry_run_validates_like_apply_unknown_name():
    store = _stub_store()
    with pytest.raises(ParameterError):
        store.dry_run({"nope": 1.0})
    assert store.snapshot() == {
        "learning_rate": 0.01, "batch_size": 32,
        "use_fp16": False, "schedule": "cosine"}


def test_dry_run_validates_like_apply_out_of_bounds():
    store = _stub_store()
    with pytest.raises(ParameterError):
        store.dry_run({"learning_rate": 9.99})
    assert store.get("learning_rate") == 0.01


def test_dry_run_validates_like_apply_wrong_type():
    store = _stub_store()
    with pytest.raises(ParameterError):
        store.dry_run({"batch_size": "lots"})
    assert store.get("batch_size") == 32


def test_dry_run_uses_coerced_values_in_report():
    store = _stub_store()
    report = store.dry_run({"learning_rate": 1})  # int coerced to float
    assert report["would_change"]["learning_rate"] == {"old": 0.01,
                                                       "new": 1.0}
    assert isinstance(report["would_change"]["learning_rate"]["new"], float)


def test_apply_still_mutates_after_dry_run():
    store = _stub_store()
    store.dry_run({"learning_rate": 0.05})
    applied = store.apply({"learning_rate": 0.05})
    assert applied == {"learning_rate": 0.05}
    assert store.get("learning_rate") == 0.05
