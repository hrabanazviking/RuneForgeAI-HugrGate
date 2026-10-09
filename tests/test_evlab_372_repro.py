"""Slice 372 — Reproducibility manifests.

Covers: manifest building (dataset/backend/policy/seed capture),
environment check passing on the same machine, version/SHA
mismatch detection, manifest_for_run derivation, bundle
integration (write/read round-trip), validation, and
serialization round-trips.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionPolicy, __version__
from hugrgate.errors import EvalError
from hugrgate.evlab import (
    ReproCheck,
    ReproManifest,
    build_repro_manifest,
    check_reproducibility,
    manifest_for_run,
    read_bundle,
    write_bundle,
)
from hugrgate.evlab.api import RunRecord


def _dataset():
    return {
        "name": "repro-smoke",
        "version": "2.1.0",
        "items": [{"state": {"x": 1}, "expected": "a"}],
    }


def _record():
    return RunRecord(
        run_id="r9", experiment_name="exp", seed=4,
        started_at="2026-10-09T12:00:00",
        finished_at="2026-10-09T12:00:01", elapsed_s=1.0,
        hugrgate_version=__version__, python_version="3.12",
        platform={"os": "linux"}, dataset_name="repro-smoke",
        dataset_version="2.1.0", dataset_fingerprint="fp9",
        policy={"k": "v"}, privacy_class="open",
        tags={"command": "pytest -q"}, backends={"stub": {"a": 1}},
        n_items=1, git_sha="deadbeef")


# --- building -----------------------------------------------------------------------------------

def test_build_manifest():
    manifest = build_repro_manifest(
        _dataset(), ["stub", "other"],
        policy=DecisionPolicy(), seed=7,
        command="pytest tests/", extra={"note": "x"})
    assert manifest.dataset_name == "repro-smoke"
    assert manifest.dataset_version == "2.1.0"
    assert manifest.dataset_fingerprint  # computed from items
    assert manifest.backends == ["stub", "other"]
    assert manifest.seed == 7
    assert manifest.command == "pytest tests/"
    assert manifest.extra == {"note": "x"}
    assert manifest.hugrgate_version == __version__
    assert manifest.created_at


def test_build_uses_explicit_fingerprint():
    ds = _dataset()
    ds["fingerprint"] = "explicit-fp"
    manifest = build_repro_manifest(ds, ["stub"])
    assert manifest.dataset_fingerprint == "explicit-fp"


def test_build_validation():
    with pytest.raises(EvalError):
        build_repro_manifest({"version": "1"}, ["stub"])
    with pytest.raises(EvalError):
        build_repro_manifest(_dataset(), [])


def test_manifest_for_run():
    manifest = manifest_for_run(_record())
    assert manifest.dataset_name == "repro-smoke"
    assert manifest.seed == 4
    assert manifest.command == "pytest -q"
    assert manifest.git_sha == "deadbeef"
    assert manifest.extra["run_id"] == "r9"
    with pytest.raises(EvalError):
        manifest_for_run({"run_id": "x"})


# --- environment check ------------------------------------------------------------------------------

def test_check_passes_on_same_environment():
    manifest = build_repro_manifest(_dataset(), ["stub"])
    check = check_reproducibility(manifest)
    assert check.ok and check.mismatches == []
    check.assert_ok()  # must not raise


def test_version_mismatch():
    manifest = build_repro_manifest(_dataset(), ["stub"])
    manifest.hugrgate_version = "0.0.0-nope"
    check = check_reproducibility(manifest)
    assert not check.ok
    assert any("hugrgate_version" in m for m in check.mismatches)
    with pytest.raises(EvalError):
        check.assert_ok()


def test_python_mismatch():
    manifest = build_repro_manifest(_dataset(), ["stub"])
    manifest.python_version = "2.7.0"
    check = check_reproducibility(manifest)
    assert not check.ok
    assert any("python_version" in m for m in check.mismatches)


def test_git_sha_mismatch_only_when_both_known():
    manifest = build_repro_manifest(_dataset(), ["stub"])
    manifest.git_sha = "0" * 40
    check = check_reproducibility(manifest)
    # Current env has a SHA (we are inside a git worktree); mismatch
    # must be reported, not silently ignored.
    assert any("git_sha" in m for m in check.mismatches)
    manifest.git_sha = None
    check = check_reproducibility(manifest)
    assert all("git_sha" not in m for m in check.mismatches)


def test_check_rejects_wrong_type():
    with pytest.raises(EvalError):
        check_reproducibility({"ok": True})


def test_check_roundtrip():
    manifest = build_repro_manifest(_dataset(), ["stub"])
    check = check_reproducibility(manifest)
    d = check.to_dict()
    assert ReproCheck(**d).to_dict() == d


# --- bundle integration ---------------------------------------------------------------------------------

def test_bundle_carries_repro_manifest(tmp_path):
    manifest = build_repro_manifest(_dataset(), ["stub"], seed=3)
    root = write_bundle(tmp_path / "b", name="repro",
                        repro_manifest=manifest)
    payload = read_bundle(root)
    assert payload["repro_manifest"]["seed"] == 3
    assert payload["repro_manifest"]["dataset_name"] == "repro-smoke"
    with pytest.raises(EvalError):
        write_bundle(tmp_path / "b2", name="x",
                     repro_manifest={"seed": 1})


def test_manifest_roundtrip():
    manifest = build_repro_manifest(_dataset(), ["stub"], seed=3)
    clone = ReproManifest.from_dict(manifest.to_dict())
    assert clone.to_dict() == manifest.to_dict()
