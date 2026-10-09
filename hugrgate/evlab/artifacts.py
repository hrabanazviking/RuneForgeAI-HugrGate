"""Artifact bundles — portable evaluation packages. Slice 371.

A lab result that only exists in memory is a rumor.  This module
packs an evaluation's outputs — dataset manifest, run record,
report dicts, arbitrary files — into a directory (or zip) with a
sha256-indexed ``bundle.json``.  :func:`verify_bundle` rehashes
every entry and fails loudly on tampering or missing files, so a
bundle can be handed to another machine (or the future) and trusted.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hugrgate import __version__
from hugrgate.errors import EvalError
from hugrgate.evlab.api import RunRecord
from hugrgate.evlab.dataset import DatasetManifest
from hugrgate.evlab.repro import ReproManifest

__all__ = [
    "BundleReport",
    "read_bundle",
    "verify_bundle",
    "write_bundle",
    "zip_bundle",
]

_INDEX = "bundle.json"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BundleReport:
    """Result of :func:`verify_bundle` (slice 371)."""

    path: str
    name: str
    files: int
    ok: bool
    problems: list[str]

    def assert_ok(self) -> None:
        if not self.ok:
            raise EvalError(
                f"bundle {self.path!r} failed verification: "
                + "; ".join(self.problems),
                problems=self.problems,
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "files": self.files,
            "ok": self.ok,
            "problems": list(self.problems),
        }


def write_bundle(
    path: str | Path,
    name: str,
    run_record: RunRecord | None = None,
    dataset_manifest: DatasetManifest | None = None,
    repro_manifest: ReproManifest | None = None,
    reports: Mapping[str, Mapping[str, Any]] | None = None,
    files: Mapping[str, str | bytes] | None = None,
) -> Path:
    """Write a bundle directory; return its path.

    Layout: ``bundle.json`` index, ``run_record.json``,
    ``dataset_manifest.json``, ``repro_manifest.json``,
    ``reports/<name>.json``, ``files/<name>``.
    """
    if not name:
        raise EvalError("bundle name must be a non-empty string")
    root = Path(path)
    if root.exists():
        raise EvalError(f"bundle path {str(root)!r} already exists")
    entries: dict[str, str] = {}

    def _put(rel: str, data: bytes) -> None:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        entries[rel] = _sha256(data)

    root.mkdir(parents=True)
    if run_record is not None:
        if not isinstance(run_record, RunRecord):
            raise EvalError("run_record must be a RunRecord")
        _put("run_record.json",
             json.dumps(run_record.to_dict(), indent=2,
                        sort_keys=True).encode())
    if dataset_manifest is not None:
        if not isinstance(dataset_manifest, DatasetManifest):
            raise EvalError("dataset_manifest must be a DatasetManifest")
        _put("dataset_manifest.json",
             json.dumps(dataset_manifest.to_dict(), indent=2,
                        sort_keys=True).encode())
    if repro_manifest is not None:
        if not isinstance(repro_manifest, ReproManifest):
            raise EvalError("repro_manifest must be a ReproManifest")
        _put("repro_manifest.json",
             json.dumps(repro_manifest.to_dict(), indent=2,
                        sort_keys=True).encode())
    for report_name, report in (reports or {}).items():
        if not report_name or "/" in report_name or "\\" in report_name:
            raise EvalError(
                f"invalid report name {report_name!r}")
        _put(f"reports/{report_name}.json",
             json.dumps(dict(report), indent=2,
                        sort_keys=True).encode())
    for file_name, content in (files or {}).items():
        if (not file_name or file_name.startswith("/")
                or ".." in Path(file_name).parts):
            raise EvalError(f"invalid file name {file_name!r}")
        data = content.encode() if isinstance(content, str) else bytes(
            content)
        _put(f"files/{file_name}", data)
    index = {
        "name": name,
        "created_at": _utcnow(),
        "hugrgate_version": __version__,
        "files": entries,
    }
    (root / _INDEX).write_text(
        json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
    return root


def _load_index(root: Path) -> Mapping[str, Any]:
    index_path = root / _INDEX
    if not index_path.is_file():
        raise EvalError(
            f"{str(root)!r} is not a bundle: {_INDEX} missing")
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise EvalError(
            f"bundle index {index_path} is corrupt: {e}") from e


def verify_bundle(path: str | Path) -> BundleReport:
    """Rehash every indexed file; report tampering or loss."""
    problems: list[str] = []
    given = Path(path)
    if given.is_file() and given.suffix == ".zip":
        tmp = Path(tempfile.mkdtemp(prefix="bundle-verify-"))
        try:
            with zipfile.ZipFile(given) as zf:
                zf.extractall(tmp)
            roots = [p for p in tmp.iterdir() if p.is_dir()]
            root = roots[0] if len(roots) == 1 else tmp
            report = verify_bundle(root)
            report.path = str(given)
            return report
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    root = given
    try:
        index = _load_index(root)
    except EvalError as e:
        return BundleReport(path=str(given), name="", files=0, ok=False,
                            problems=[str(e)])
    name = str(index.get("name", ""))
    entries = index.get("files", {})
    if not isinstance(entries, dict):
        return BundleReport(path=str(given), name=name, files=0,
                            ok=False,
                            problems=["bundle index 'files' is not a map"])
    for rel, expected in entries.items():
        target = root / rel
        if not target.is_file():
            problems.append(f"missing file: {rel}")
            continue
        actual = _sha256(target.read_bytes())
        if actual != expected:
            problems.append(f"hash mismatch: {rel}")
    return BundleReport(path=str(given), name=name,
                        files=len(entries), ok=not problems,
                        problems=problems)


def read_bundle(path: str | Path) -> dict[str, Any]:
    """Verify then load a bundle's index and JSON payloads."""
    report = verify_bundle(path)
    report.assert_ok()
    root = Path(path)
    if root.is_file() and root.suffix == ".zip":
        tmp = Path(tempfile.mkdtemp(prefix="bundle-read-"))
        with zipfile.ZipFile(root) as zf:
            zf.extractall(tmp)
        roots = [p for p in tmp.iterdir() if p.is_dir()]
        root = roots[0] if len(roots) == 1 else tmp
    index = _load_index(root)
    payload: dict[str, Any] = {
        "index": dict(index),
        "reports": {},
        "files": {},
    }
    for rel in index["files"]:
        if rel == "run_record.json":
            payload["run_record"] = json.loads(
                (root / rel).read_text(encoding="utf-8"))
        elif rel == "dataset_manifest.json":
            payload["dataset_manifest"] = json.loads(
                (root / rel).read_text(encoding="utf-8"))
        elif rel == "repro_manifest.json":
            payload["repro_manifest"] = json.loads(
                (root / rel).read_text(encoding="utf-8"))
        elif rel.startswith("reports/"):
            payload["reports"][rel[len("reports/"):-len(".json")]] = \
                json.loads((root / rel).read_text(encoding="utf-8"))
        elif rel.startswith("files/"):
            payload["files"][rel[len("files/"):]] = \
                (root / rel).read_bytes()
    return payload


def zip_bundle(path: str | Path) -> Path:
    """Pack a bundle directory into ``<name>.zip``; return its path."""
    root = Path(path)
    _load_index(root)  # fail loudly when not a bundle
    out = root.with_suffix(".zip")
    if out.exists():
        raise EvalError(f"zip target {str(out)!r} already exists")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(root.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(root.parent))
    return out
