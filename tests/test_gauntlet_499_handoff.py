"""Slice 499 — tests for the precision-audit handoff checker.

Loads tools/precision_handoff_check.py by path and covers: the
real manifest passes, missing evidence is flagged, bad schema is
flagged, missing reproduce targets are flagged, duplicate ids
are flagged.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "precision_handoff_check.py"


def _load():
    spec = importlib.util.spec_from_file_location("precision_handoff_check",
                                                  TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules["precision_handoff_check"] = module
    spec.loader.exec_module(module)
    return module


checker = _load()

REAL_MANIFEST = REPO / "docs/gauntlet/499-audit-handoff.json"


def _write_manifest(tmp_path: Path, claims) -> Path:
    manifest = {"package": "p", "handoff_version": "1",
                "date": "2026-10-09", "claims": claims}
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps(manifest))
    return path


def _repo_with(tmp_path: Path, files: list[str]) -> Path:
    repo = tmp_path / "repo"
    for f in files:
        p = repo / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
    return repo


def test_real_manifest_complete():
    report = checker.check_handoff(REAL_MANIFEST, REPO)
    assert report.complete, report.problems


def test_missing_evidence_flagged(tmp_path):
    repo = _repo_with(tmp_path, ["tests/test_x.py"])
    manifest = _write_manifest(tmp_path, [{
        "id": "C-1", "claim": "c",
        "reproduce": ["pytest tests/test_x.py"],
        "evidence": ["docs/missing.md"]}])
    report = checker.check_handoff(manifest, repo)
    assert not report.complete
    assert any("missing.md" in p for p in report.problems)


def test_missing_reproduce_target_flagged(tmp_path):
    repo = _repo_with(tmp_path, ["docs/e.md"])
    manifest = _write_manifest(tmp_path, [{
        "id": "C-1", "claim": "c",
        "reproduce": ["pytest tests/nope.py"],
        "evidence": ["docs/e.md"]}])
    report = checker.check_handoff(manifest, repo)
    assert not report.complete
    assert any("nope.py" in p for p in report.problems)


def test_bad_schema_flagged(tmp_path):
    repo = _repo_with(tmp_path, [])
    manifest = _write_manifest(tmp_path, [
        {"id": "C-1", "claim": "c"}])  # missing reproduce/evidence
    report = checker.check_handoff(manifest, repo)
    assert not report.complete
    assert any("reproduce" in p for p in report.problems)


def test_duplicate_ids_flagged(tmp_path):
    repo = _repo_with(tmp_path, ["docs/e.md", "tests/t.py"])
    claim = {"id": "C-1", "claim": "c",
             "reproduce": ["pytest tests/t.py"], "evidence": ["docs/e.md"]}
    manifest = _write_manifest(tmp_path, [claim, dict(claim)])
    report = checker.check_handoff(manifest, repo)
    assert not report.complete
    assert any("duplicate" in p for p in report.problems)


def test_unreadable_manifest(tmp_path):
    report = checker.check_handoff(tmp_path / "nope.json", tmp_path)
    assert not report.complete


def test_invalid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    report = checker.check_handoff(bad, tmp_path)
    assert not report.complete


def test_placeholder_targets_ignored(tmp_path):
    repo = _repo_with(tmp_path, [])
    manifest = _write_manifest(tmp_path, [{
        "id": "C-1", "claim": "c",
        "reproduce": ["python tools/rc_build.py --builder-python <python-with-build>"],
        "evidence": []}])
    report = checker.check_handoff(manifest, repo)
    # Only the tools/rc_build.py target is checked; the placeholder is not.
    assert any("rc_build.py" in p for p in report.problems)
    assert not any("python-with-build" in p for p in report.problems)
