"""Slice 375 — Release gate (Campaign XV capstone).

Covers: clean release, gate-failure hold, regression hold,
repro-mismatch hold, missing-manifest hold (and opt-out),
missing-SHA hold (and opt-out), gateless-suite refusal,
validation of inputs and regression triples, assert_release
raise/pass, and verdict serialization.
"""

from __future__ import annotations

import pytest

from hugrgate import __version__
from hugrgate.errors import EvalError, EvalGateError
from hugrgate.evlab import (
    HOLD,
    RELEASE,
    Gate,
    GateSuite,
    HistoryStore,
    ReleaseVerdict,
    assert_release,
    build_repro_manifest,
    release_gate,
)
from hugrgate.evlab.api import RunRecord


def _record(accuracy=0.92, sha="abc123"):
    return RunRecord(
        run_id="rel-1", experiment_name="exp", seed=1,
        started_at="2026-10-09T12:00:00",
        finished_at="2026-10-09T12:00:01", elapsed_s=1.0,
        hugrgate_version=__version__, python_version="3.12",
        platform={"os": "linux"}, dataset_name="ship",
        dataset_version="1.0.0", dataset_fingerprint="fp",
        policy={}, privacy_class="open", tags={},
        backends={"stub": {"accuracy": accuracy}}, n_items=50,
        git_sha=sha)


def _gates(threshold=0.8):
    return GateSuite(name="ship-gates", gates=[
        Gate(name="acc-floor", metric="accuracy", op=">=",
             threshold=threshold)])


def _repro():
    return build_repro_manifest(
        {"name": "ship", "version": "1.0.0", "items": []}, ["stub"])


# --- happy path -------------------------------------------------------------------------------------

def test_clean_release():
    verdict = release_gate(_record(), _gates(), repro_manifest=_repro())
    assert verdict.decision == RELEASE
    assert verdict.released is True
    assert verdict.reasons == []
    assert verdict.run_id == "rel-1"
    assert verdict.dataset == "ship"
    assert len(verdict.gate_results) == 1
    assert assert_release(verdict) is verdict


def test_gate_failure_holds():
    verdict = release_gate(_record(accuracy=0.5), _gates(),
                           repro_manifest=_repro())
    assert verdict.decision == HOLD
    assert len(verdict.reasons) == 1
    assert "acc-floor" in verdict.reasons[0]
    with pytest.raises(EvalGateError) as ei:
        assert_release(verdict)
    assert "HOLD" in str(ei.value)
    assert ei.value.details["run_id"] == "rel-1"


def test_regression_holds(tmp_path):
    store = HistoryStore(tmp_path / "h.jsonl")
    store.append(_record(accuracy=0.95))
    verdict = release_gate(
        _record(accuracy=0.70), _gates(threshold=0.5), history=store,
        regression_metrics=[("accuracy", 0.02, True)],
        repro_manifest=_repro())
    assert verdict.decision == HOLD
    assert len(verdict.regressions) == 1
    assert any("regression" in r for r in verdict.reasons)


def test_no_regression_still_releases(tmp_path):
    store = HistoryStore(tmp_path / "h.jsonl")
    store.append(_record(accuracy=0.90))
    verdict = release_gate(
        _record(accuracy=0.92), _gates(), history=store,
        regression_metrics=[("accuracy", 0.02, True)],
        repro_manifest=_repro())
    assert verdict.decision == RELEASE


def test_repro_mismatch_holds():
    manifest = _repro()
    manifest.hugrgate_version = "0.0.0-nope"
    verdict = release_gate(_record(), _gates(),
                           repro_manifest=manifest)
    assert verdict.decision == HOLD
    assert any("reproducibility" in r for r in verdict.reasons)
    assert verdict.repro_check["ok"] is False


def test_missing_manifest_holds_when_required():
    verdict = release_gate(_record(), _gates(), repro_manifest=None)
    assert verdict.decision == HOLD
    assert any("reproducibility manifest" in r
               for r in verdict.reasons)
    verdict = release_gate(_record(), _gates(), repro_manifest=None,
                           require_repro=False)
    assert verdict.decision == RELEASE


def test_missing_sha_holds_when_required():
    verdict = release_gate(_record(sha=None), _gates(),
                           repro_manifest=_repro())
    assert verdict.decision == HOLD
    assert any("git SHA" in r for r in verdict.reasons)
    verdict = release_gate(_record(sha=None), _gates(),
                           repro_manifest=_repro(),
                           require_git_sha=False)
    assert verdict.decision == RELEASE


def test_multiple_reasons_accumulate():
    manifest = _repro()
    manifest.hugrgate_version = "0.0.0-nope"
    verdict = release_gate(_record(accuracy=0.1, sha=None),
                           _gates(), repro_manifest=manifest)
    assert verdict.decision == HOLD
    assert len(verdict.reasons) == 3  # gate + repro + sha


# --- validation ----------------------------------------------------------------------------------------

def test_gateless_suite_refused():
    with pytest.raises(EvalError):
        release_gate(_record(), GateSuite(name="empty", gates=[]),
                     repro_manifest=_repro())


def test_regression_metrics_need_history():
    with pytest.raises(EvalError):
        release_gate(_record(), _gates(),
                     regression_metrics=[("accuracy", 0.02, True)],
                     repro_manifest=_repro())


def test_bad_regression_triple():
    with pytest.raises(EvalError):
        release_gate(_record(), _gates(), history=None,
                     regression_metrics=["accuracy"],
                     repro_manifest=_repro(),
                     require_repro=False)


def test_wrong_types_rejected():
    with pytest.raises(EvalError):
        release_gate({"run_id": "x"}, _gates())
    with pytest.raises(EvalError):
        release_gate(_record(), {"name": "x"})
    with pytest.raises(EvalError):
        assert_release({"decision": "release"})


def test_verdict_roundtrip():
    verdict = release_gate(_record(accuracy=0.5), _gates(),
                           repro_manifest=_repro())
    clone = ReleaseVerdict.from_dict(verdict.to_dict())
    assert clone.to_dict() == verdict.to_dict()
    assert clone.decision == HOLD
    assert RELEASE == "release" and HOLD == "hold"
