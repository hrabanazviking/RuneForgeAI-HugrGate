"""Model manifests and a disk-backed versioned model store. Slice 25.

A :class:`ModelManifest` describes *what* a trained model is (name, version,
backend, feature schema, classes, training metrics) while the :class:`ModelStore`
keeps manifests next to their weight payloads on disk, with a SHA-256
integrity hash so tampering or truncated writes are caught on load.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hugrgate.errors import HugrGateError

__all__ = [
    "ModelManifest",
    "ModelStore",
    "sha256_bytes",
]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(payload: bytes) -> str:
    """SHA-256 hex digest of a payload."""
    return hashlib.sha256(payload).hexdigest()


@dataclass
class ModelManifest:
    """Versioned description of one trained model artifact."""

    name: str
    version: str
    backend: str
    spec_type: str
    features: list[str]
    classes: list[str]
    trained_at: str = field(default_factory=_utcnow_iso)
    metrics: dict[str, float] = field(default_factory=dict)
    payload_hash: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.name:
            raise HugrGateError("manifest needs a name")
        if not self.version:
            raise HugrGateError("manifest needs a version")
        if len(set(self.classes)) != len(self.classes):
            raise HugrGateError("manifest classes must be unique")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ModelManifest:
        return cls(
            name=d["name"],
            version=d["version"],
            backend=d["backend"],
            spec_type=d["spec_type"],
            features=list(d["features"]),
            classes=list(d["classes"]),
            trained_at=d.get("trained_at", _utcnow_iso()),
            metrics=dict(d.get("metrics", {})),
            payload_hash=d.get("payload_hash", ""),
            extra=dict(d.get("extra", {})),
        )

    @classmethod
    def from_json(cls, text: str) -> ModelManifest:
        return cls.from_dict(json.loads(text))

    def verify(self, payload: bytes) -> None:
        """Raise if the payload does not match the recorded hash."""
        if not self.payload_hash:
            raise HugrGateError(
                f"manifest {self.name}@{self.version} has no payload hash")
        digest = sha256_bytes(payload)
        if digest != self.payload_hash:
            raise HugrGateError(
                f"integrity check failed for {self.name}@{self.version}: "
                f"expected {self.payload_hash[:16]}…, got {digest[:16]}…")


class ModelStore:
    """Disk-backed, versioned registry of model artifacts.

    Layout: ``<root>/<name>/<version>/{manifest.json, model.bin}``.
    """

    MANIFEST_FILE = "manifest.json"
    PAYLOAD_FILE = "model.bin"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _version_dir(self, name: str, version: str) -> Path:
        return self.root / name / version

    def put(self, manifest: ModelManifest, payload: bytes) -> Path:
        """Store a manifest + payload. Returns the version directory."""
        manifest.payload_hash = sha256_bytes(payload)
        vdir = self._version_dir(manifest.name, manifest.version)
        if vdir.exists():
            raise HugrGateError(
                f"model {manifest.name}@{manifest.version} already stored; "
                f"use a new version or delete it first")
        vdir.mkdir(parents=True)
        (vdir / self.MANIFEST_FILE).write_text(manifest.to_json())
        (vdir / self.PAYLOAD_FILE).write_bytes(payload)
        return vdir

    def get(self, name: str,
            version: str | None = None) -> tuple[ModelManifest, bytes]:
        """Fetch ``(manifest, payload)``; latest version when omitted.

        The payload hash is verified before anything is returned.
        """
        if version is None:
            version = self.latest_version(name)
        vdir = self._version_dir(name, version)
        if not vdir.is_dir():
            raise HugrGateError(f"no stored model {name}@{version}")
        manifest = ModelManifest.from_json(
            (vdir / self.MANIFEST_FILE).read_text())
        payload = (vdir / self.PAYLOAD_FILE).read_bytes()
        manifest.verify(payload)
        return manifest, payload

    def list_versions(self, name: str) -> list[str]:
        ndir = self.root / name
        if not ndir.is_dir():
            return []
        return sorted(p.name for p in ndir.iterdir() if p.is_dir())

    def latest_version(self, name: str) -> str:
        versions = self.list_versions(name)
        if not versions:
            raise HugrGateError(f"no stored versions of model {name!r}")
        return versions[-1]

    def list_models(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_dir())

    def delete(self, name: str, version: str) -> None:
        vdir = self._version_dir(name, version)
        if not vdir.is_dir():
            raise HugrGateError(f"no stored model {name}@{version}")
        shutil.rmtree(vdir)
