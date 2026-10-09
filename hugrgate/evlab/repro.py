"""Reproducibility manifests — replay recipes. Slice 372.

A result without a recipe is an anecdote.  A :class:`ReproManifest`
captures everything needed to replay an evaluation: dataset
identity + fingerprint, backends, policy, seed, the exact
hugrgate/python versions, platform, best-effort git SHA, and the
command that produced it.  :func:`check_reproducibility` compares a
manifest against the *current* environment and names every
mismatch, so "works on my machine" becomes a checkable claim.
Manifests ride inside artifact bundles as ``repro_manifest.json``.
"""

from __future__ import annotations

import platform as _platform
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from hugrgate import __version__
from hugrgate.errors import EvalError
from hugrgate.evlab.api import RunRecord
from hugrgate.evlab.dataset import fingerprint_items
from hugrgate.policy import DecisionPolicy

__all__ = [
    "ReproCheck",
    "ReproManifest",
    "build_repro_manifest",
    "check_reproducibility",
    "manifest_for_run",
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    sha = out.stdout.strip()
    return sha or None


def _platform_info() -> dict[str, str]:
    return {
        "system": _platform.system(),
        "release": _platform.release(),
        "machine": _platform.machine(),
    }


@dataclass
class ReproManifest:
    """Everything needed to replay one evaluation (slice 372)."""

    dataset_name: str
    dataset_version: str
    dataset_fingerprint: str
    backends: list[str]
    policy: dict[str, Any]
    seed: int
    hugrgate_version: str
    python_version: str
    platform: dict[str, str]
    git_sha: str | None
    command: str | None
    created_at: str
    extra: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "dataset_version": self.dataset_version,
            "dataset_fingerprint": self.dataset_fingerprint,
            "backends": list(self.backends),
            "policy": dict(self.policy),
            "seed": self.seed,
            "hugrgate_version": self.hugrgate_version,
            "python_version": self.python_version,
            "platform": dict(self.platform),
            "git_sha": self.git_sha,
            "command": self.command,
            "created_at": self.created_at,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReproManifest:
        return cls(
            dataset_name=data["dataset_name"],
            dataset_version=data["dataset_version"],
            dataset_fingerprint=data["dataset_fingerprint"],
            backends=list(data["backends"]),
            policy=dict(data["policy"]),
            seed=data["seed"],
            hugrgate_version=data["hugrgate_version"],
            python_version=data["python_version"],
            platform=dict(data["platform"]),
            git_sha=data.get("git_sha"),
            command=data.get("command"),
            created_at=data["created_at"],
            extra=dict(data.get("extra", {})),
        )


@dataclass
class ReproCheck:
    """Result of :func:`check_reproducibility` (slice 372)."""

    ok: bool
    mismatches: list[str]

    def assert_ok(self) -> None:
        if not self.ok:
            raise EvalError(
                "environment does not match reproducibility manifest: "
                + "; ".join(self.mismatches),
                mismatches=self.mismatches,
            )

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "mismatches": list(self.mismatches)}


def build_repro_manifest(
    dataset: Mapping[str, Any],
    backends: Sequence[str],
    policy: DecisionPolicy | None = None,
    seed: int = 0,
    command: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> ReproManifest:
    """Build a manifest for an evaluation about to run (or just run)."""
    name = dataset.get("name")
    version = dataset.get("version")
    if not name or not version:
        raise EvalError(
            "repro manifest needs dataset 'name' and 'version'")
    fingerprint = dataset.get("fingerprint") or fingerprint_items(
        list(dataset.get("items", [])))
    backend_names = list(backends)
    if not backend_names:
        raise EvalError("repro manifest needs at least one backend")
    return ReproManifest(
        dataset_name=str(name),
        dataset_version=str(version),
        dataset_fingerprint=str(fingerprint),
        backends=backend_names,
        policy=dict((policy or DecisionPolicy()).to_dict()),
        seed=seed,
        hugrgate_version=__version__,
        python_version=_platform.python_version(),
        platform=_platform_info(),
        git_sha=_git_sha(),
        command=command,
        created_at=_utcnow(),
        extra=dict(extra or {}),
    )


def manifest_for_run(record: RunRecord) -> ReproManifest:
    """Derive a manifest from a finished :class:`RunRecord`."""
    if not isinstance(record, RunRecord):
        raise EvalError(
            f"manifest_for_run needs a RunRecord, got "
            f"{type(record).__name__}")
    return ReproManifest(
        dataset_name=record.dataset_name,
        dataset_version=record.dataset_version,
        dataset_fingerprint=record.dataset_fingerprint,
        backends=sorted(record.backends),
        policy=dict(record.policy),
        seed=record.seed,
        hugrgate_version=record.hugrgate_version,
        python_version=record.python_version,
        platform=dict(record.platform),
        git_sha=record.git_sha,
        command=record.tags.get("command"),
        created_at=record.finished_at,
        extra={"run_id": record.run_id,
               "experiment_name": record.experiment_name},
    )


def check_reproducibility(
    manifest: ReproManifest,
) -> ReproCheck:
    """Compare a manifest against the current environment.

    Checks hugrgate version, Python version, and git SHA (when the
    manifest records one and one is available now).  Platform details
    are recorded for forensics, not compared — an OS upgrade should
    not fail a replay check.
    """
    if not isinstance(manifest, ReproManifest):
        raise EvalError(
            f"check_reproducibility needs a ReproManifest, got "
            f"{type(manifest).__name__}")
    mismatches: list[str] = []
    if manifest.hugrgate_version != __version__:
        mismatches.append(
            f"hugrgate_version: manifest {manifest.hugrgate_version!r} "
            f"!= current {__version__!r}")
    current_python = _platform.python_version()
    if manifest.python_version != current_python:
        mismatches.append(
            f"python_version: manifest {manifest.python_version!r} "
            f"!= current {current_python!r}")
    current_sha = _git_sha()
    if (manifest.git_sha is not None and current_sha is not None
            and manifest.git_sha != current_sha):
        mismatches.append(
            f"git_sha: manifest {manifest.git_sha[:12]!r} != "
            f"current {current_sha[:12]!r}")
    return ReproCheck(ok=not mismatches, mismatches=mismatches)
