"""Slice 267 — dependency failure matrix tests."""

from __future__ import annotations

import json
from unittest import mock

import pytest

from hugrgate.chaos import (
    DependencyMatrix,
    DependencyScenario,
    builtin_dependency_matrix,
    dependency_failure_matrix,
)
from hugrgate.core import HugrGate
from hugrgate.errors import SpecError
from hugrgate.spec import DecisionSpec
from tests.conftest import StubBackend


def _spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def _scenario(name="s", break_it=None, check=None):
    return DependencyScenario(
        name=name,
        description=f"scenario {name}",
        break_it=break_it or (lambda: (lambda: None)),
        check=check or (lambda: None),
    )


# --- builtin matrix -------------------------------------------------------------------------------------

def test_builtin_matrix_all_survive():
    report = dependency_failure_matrix()
    assert report["all_survived"] is True, report
    assert report["scenarios"] == 3
    assert report["failed"] == []
    assert sorted(r["name"] for r in report["results"]) == [
        "embedding-numpy-missing",
        "ml-numpy-missing",
        "ml-sklearn-missing",
    ]
    json.dumps(report)


def test_builtin_matrix_restores_patched_modules():
    import hugrgate.backends.embedding as embedding
    import hugrgate.backends.logreg as logreg
    real_np = embedding.np
    dependency_failure_matrix()
    assert embedding.np is real_np
    assert logreg.np is not None
    assert logreg.LogisticRegression is not None


# --- matrix mechanics --------------------------------------------------------------------------------------

def test_matrix_never_aborts_and_always_restores():
    restored: list[str] = []
    matrix = DependencyMatrix()
    matrix.add(_scenario("ok"))
    matrix.add(_scenario(
        "check-fails",
        break_it=lambda: lambda: restored.append("check-fails"),
        check=lambda: (_ for _ in ()).throw(AssertionError("boom"))))
    matrix.add(_scenario(
        "break-fails",
        break_it=lambda: (_ for _ in ()).throw(RuntimeError("x"))))
    report = matrix.run_all()
    assert report["all_survived"] is False
    assert report["failed"] == ["break-fails", "check-fails"]
    assert restored == ["check-fails"]  # restore ran despite check failure
    assert matrix.scenarios() == ["break-fails", "check-fails", "ok"]


def test_matrix_restore_failure_marks_not_survived():
    def break_it():
        def restore():
            raise OSError("cannot restore")
        return restore
    matrix = DependencyMatrix()
    matrix.add(_scenario("flaky-restore", break_it=break_it))
    report = matrix.run_all()
    assert report["all_survived"] is False
    assert "restore failed" in report["results"][0]["detail"]


def test_matrix_rejects_bad_scenarios():
    matrix = DependencyMatrix()
    with pytest.raises(SpecError, match="can only add"):
        matrix.add("nope")  # type: ignore[arg-type]
    matrix.add(_scenario("dup"))
    with pytest.raises(SpecError, match="duplicate"):
        matrix.add(_scenario("dup"))
    with pytest.raises(SpecError, match="non-empty"):
        DependencyScenario("", "d", lambda: (lambda: None), lambda: None)
    with pytest.raises(SpecError, match="non-empty"):
        DependencyScenario("n", " ", lambda: (lambda: None), lambda: None)


# --- the slice's hardening: provenance failure must not fail decisions ---------------------------------------

def test_provenance_store_failure_does_not_fail_decisions():
    gate = HugrGate()
    gate.register(StubBackend(name="s", value="b"))

    def break_it():
        patcher = mock.patch.object(
            gate.provenance, "append",
            side_effect=OSError("provenance disk gone"))
        mocked = patcher.start()

        def restore():
            patcher.stop()
            # Non-vacuous: the decision path must actually attempt the
            # provenance write (otherwise the scenario proves nothing).
            assert mocked.called, "provenance.append was never attempted"
        return restore

    def check():
        result = gate.decide({}, _spec(), backend_name="s")
        assert result.accepted is True
        assert result.value == "b"

    matrix = builtin_dependency_matrix()
    matrix.add(DependencyScenario(
        "provenance-store-down",
        "provenance append() raises: decide() must still return the "
        "decision (observability degrades, decisions don't)",
        break_it, check))
    report = matrix.run_all()
    assert report["all_survived"] is True, report
    assert report["scenarios"] == 4
