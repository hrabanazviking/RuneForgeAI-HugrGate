"""Model checksum enforcement. Slice 406.

Signed metadata (slice 405) attests *claims* about a model; checksums
attest the *bytes*. A manifest pins every file in a model directory
to a SHA-256 digest; :func:`verify_manifest` re-hashes on load and
:meth:`ModelChecksumGate.load` refuses to hand a loader bytes that do
not match. Tampered, truncated, or substituted weight files fail
closed with :class:`SignatureVerificationFailed`.

Hashing is streaming (64 KiB chunks) so multi-gigabyte weight files
never sit fully in memory.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hugrgate.errors import SignatureVerificationFailed
from hugrgate.security.path_guards import safe_join

__all__ = [
    "ChecksumManifest",
    "ModelChecksumGate",
    "VerificationReport",
    "build_manifest",
    "hash_file",
    "verified_open",
    "verify_manifest",
]

_CHUNK = 65536
_ALGORITHM = "sha256"


def hash_file(path: str | Path) -> str:
    """Streaming SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class ChecksumManifest:
    """Pinned digests for every file in a model directory."""

    files: dict[str, str] = field(default_factory=dict)  # relpath -> hex
    algorithm: str = _ALGORITHM

    def to_dict(self) -> dict[str, Any]:
        return {"algorithm": self.algorithm, "files": dict(self.files)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChecksumManifest:
        algorithm = str(data.get("algorithm", _ALGORITHM))
        if algorithm != _ALGORITHM:
            raise SignatureVerificationFailed(
                f"unsupported checksum algorithm {algorithm!r}")
        files = data.get("files", {})
        if not isinstance(files, dict):
            raise SignatureVerificationFailed(
                "checksum manifest 'files' must be a mapping")
        return cls(files={str(k): str(v) for k, v in files.items()},
                   algorithm=algorithm)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> ChecksumManifest:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise SignatureVerificationFailed(
                f"checksum manifest is not valid JSON: {e}") from e
        if not isinstance(data, dict):
            raise SignatureVerificationFailed(
                "checksum manifest must be a JSON object")
        return cls.from_dict(data)


@dataclass
class VerificationReport:
    ok: list[str] = field(default_factory=list)
    mismatched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.mismatched and not self.missing

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "ok": sorted(self.ok),
            "mismatched": sorted(self.mismatched),
            "missing": sorted(self.missing),
            "extra": sorted(self.extra),
        }


def build_manifest(root: str | Path,
                   manifest_name: str = "checksums.json") -> ChecksumManifest:
    """Hash every regular file under ``root`` (except the manifest)."""
    root = Path(root)
    manifest = ChecksumManifest()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == manifest_name:
            continue
        rel = path.relative_to(root).as_posix()
        manifest.files[rel] = hash_file(path)
    return manifest


def verify_manifest(root: str | Path, manifest: ChecksumManifest,
                    strict: bool = False) -> VerificationReport:
    """Re-hash ``root`` against the manifest.

    ``strict=True`` also reports files present on disk but absent
    from the manifest (an attacker-added file).
    """
    root = Path(root)
    report = VerificationReport()
    on_disk = {p.relative_to(root).as_posix()
               for p in root.rglob("*") if p.is_file()}
    for rel, expected in manifest.files.items():
        path = root / rel
        if not path.is_file():
            report.missing.append(rel)
        elif hash_file(path) != expected:
            report.mismatched.append(rel)
        else:
            report.ok.append(rel)
    if strict:
        report.extra = sorted(on_disk - set(manifest.files))
    return report


def enforce_manifest(root: str | Path, manifest: ChecksumManifest,
                     strict: bool = False) -> VerificationReport:
    """Like :func:`verify_manifest` but raises on any failure."""
    report = verify_manifest(root, manifest, strict=strict)
    problems = ([f"mismatched: {n}" for n in report.mismatched]
                + [f"missing: {n}" for n in report.missing]
                + ([f"extra: {n}" for n in report.extra] if strict else []))
    if problems:
        raise SignatureVerificationFailed(
            "model checksum verification failed: " + "; ".join(problems),
            mismatched=sorted(report.mismatched),
            missing=sorted(report.missing),
            extra=sorted(report.extra))
    return report


def verified_open(root: str | Path, relpath: str,
                  manifest: ChecksumManifest):
    """Open ``relpath`` for reading after verifying its checksum.

    Returns a binary file object; raises SignatureVerificationFailed
    when the file is absent from the manifest or does not match.
    The path is jailed to ``root`` via :func:`safe_join` (slice 412),
    so manifest keys cannot be traversal payloads either.
    """
    root = Path(root)
    expected = manifest.files.get(relpath)
    if expected is None:
        raise SignatureVerificationFailed(
            f"{relpath!r} is not pinned in the checksum manifest")
    path = safe_join(root, relpath)
    if not path.is_file() or hash_file(path) != expected:
        raise SignatureVerificationFailed(
            f"checksum mismatch for {relpath!r}")
    return open(path, "rb")


class ModelChecksumGate:
    """Verify-then-load gate for model directories.

    ``loader`` is any callable ``(root: Path) -> T`` (e.g. a pack
    loader); :meth:`load` verifies the manifest first and only then
    invokes it, so untrusted bytes never reach the parser.
    """

    def __init__(self, manifest: ChecksumManifest, strict: bool = False,
                 manifest_name: str = "checksums.json") -> None:
        self._manifest = manifest
        self._strict = strict
        self._manifest_name = manifest_name

    def load(self, root: str | Path,
             loader: Callable[[Path], Any]) -> Any:
        root = Path(root)
        enforce_manifest(root, self._manifest, strict=self._strict)
        return loader(root)

    def write_manifest(self, root: str | Path) -> Path:
        """(Re)build and persist the manifest for ``root``."""
        manifest = build_manifest(root, self._manifest_name)
        path = Path(root) / self._manifest_name
        path.write_text(manifest.to_json(), encoding="utf-8")
        self._manifest = manifest
        return path
