"""Slice 371 — Artifact bundles.

Covers: write/verify/read round-trip, tamper detection (hash
mismatch names the file), missing-file detection, non-bundle
rejection, zip pack + verify, name/path validation, and
BundleReport.assert_ok / to_dict.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import EvalError
from hugrgate.evlab import (
    BundleReport,
    read_bundle,
    verify_bundle,
    write_bundle,
    zip_bundle,
)
from hugrgate.evlab.api import RunRecord
from hugrgate.evlab.dataset import DatasetManifest


def _record():
    return RunRecord(
        run_id="r1", experiment_name="exp", seed=1,
        started_at="2026-10-09T12:00:00",
        finished_at="2026-10-09T12:00:01", elapsed_s=1.0,
        hugrgate_version="0.1.0", python_version="3.12",
        platform={"os": "linux"}, dataset_name="ds",
        dataset_version="1.0.0", dataset_fingerprint="fp", policy={},
        privacy_class="open", tags={},
        backends={"stub": {"accuracy": 0.9}}, n_items=10)


def _manifest():
    return DatasetManifest(name="ds", version="1.0.0", spec={})


def _bundle(tmp_path, **kw):
    return write_bundle(
        tmp_path / "bundle", name="smoke", run_record=_record(),
        dataset_manifest=_manifest(),
        reports={"cv": {"mean": 0.9}},
        files={"notes.txt": "hello", "raw.bin": b"\x00\x01"},
        **kw)


# --- round trip --------------------------------------------------------------------------------

def test_write_verify_read(tmp_path):
    root = _bundle(tmp_path)
    report = verify_bundle(root)
    assert report.ok and report.files == 5
    assert report.name == "smoke"
    report.assert_ok()  # must not raise
    payload = read_bundle(root)
    assert payload["run_record"]["run_id"] == "r1"
    assert payload["dataset_manifest"]["name"] == "ds"
    assert payload["reports"]["cv"] == {"mean": 0.9}
    assert payload["files"]["notes.txt"] == b"hello"
    assert payload["files"]["raw.bin"] == b"\x00\x01"
    assert payload["index"]["name"] == "smoke"


def test_minimal_bundle(tmp_path):
    root = write_bundle(tmp_path / "b", name="empty")
    assert verify_bundle(root).ok


def test_tamper_detected(tmp_path):
    root = _bundle(tmp_path)
    (root / "reports" / "cv.json").write_text('{"mean": 0.1}')
    report = verify_bundle(root)
    assert not report.ok
    assert any("hash mismatch" in p and "cv.json" in p
               for p in report.problems)
    with pytest.raises(EvalError):
        report.assert_ok()
    with pytest.raises(EvalError):
        read_bundle(root)


def test_missing_file_detected(tmp_path):
    root = _bundle(tmp_path)
    (root / "files" / "notes.txt").unlink()
    report = verify_bundle(root)
    assert not report.ok
    assert any("missing file" in p for p in report.problems)


def test_not_a_bundle(tmp_path):
    (tmp_path / "plain").mkdir()
    report = verify_bundle(tmp_path / "plain")
    assert not report.ok
    assert "bundle.json" in report.problems[0]


def test_existing_path_rejected(tmp_path):
    _bundle(tmp_path)
    with pytest.raises(EvalError):
        write_bundle(tmp_path / "bundle", name="again")


def test_bad_names_rejected(tmp_path):
    with pytest.raises(EvalError):
        write_bundle(tmp_path / "b", name="")
    with pytest.raises(EvalError):
        write_bundle(tmp_path / "b", name="x",
                     reports={"a/b": {}})
    with pytest.raises(EvalError):
        write_bundle(tmp_path / "b", name="x",
                     files={"../evil": "x"})


def test_wrong_types_rejected(tmp_path):
    with pytest.raises(EvalError):
        write_bundle(tmp_path / "b", name="x",
                     run_record={"run_id": "r"})
    with pytest.raises(EvalError):
        write_bundle(tmp_path / "b", name="x",
                     dataset_manifest={"name": "d"})


# --- zip -------------------------------------------------------------------------------------------

def test_zip_roundtrip(tmp_path):
    root = _bundle(tmp_path)
    zipped = zip_bundle(root)
    assert zipped.suffix == ".zip"
    report = verify_bundle(zipped)
    assert report.ok and report.path == str(zipped)
    payload = read_bundle(zipped)
    assert payload["run_record"]["run_id"] == "r1"
    with pytest.raises(EvalError):
        zip_bundle(root)  # target exists
    with pytest.raises(EvalError):
        zip_bundle(tmp_path / "plain")


def test_bundle_report_dict(tmp_path):
    root = _bundle(tmp_path)
    report = verify_bundle(root)
    d = report.to_dict()
    assert d["ok"] is True and d["files"] == 5 and d["problems"] == []
    clone = BundleReport(**d)
    assert clone.to_dict() == d
