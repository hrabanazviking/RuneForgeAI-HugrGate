"""Calibration profiles. Slice 29.

A :class:`CalibrationProfile` is a named, versioned record of a fitted
calibration: which backend + model it applies to, which calibrator with
which per-class parameters, the metrics on the calibration set, and a hash
of that dataset.  Profiles are stored *separately* from model weights, so
recalibration never touches the underlying model.

:class:`CalibratedBackend` wraps any trained classifier backend, applies the
profile's per-class (one-vs-rest) calibrators to the raw distribution,
renormalizes, and stamps ``result.calibration_profile``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

from hugrgate.backend import Backend
from hugrgate.calibration import Calibrator, CalibratorRegistry
from hugrgate.errors import CalibrationError, HugrGateError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec


def hash_dataset(scores: Sequence[float],
                 labels: Sequence[int]) -> str:
    """Stable SHA-256 fingerprint of a calibration dataset."""
    s = np.asarray(list(scores), dtype=float)
    y = np.asarray(list(labels), dtype=int)
    h = hashlib.sha256()
    h.update(s.tobytes())
    h.update(y.tobytes())
    h.update(str(len(s)).encode())
    return h.hexdigest()


@dataclass
class CalibrationProfile:
    """Named, versioned record of a fitted calibration."""

    name: str
    version: str = "1.0.0"
    backend_name: str = ""
    model_name: str = ""
    model_version: str = ""
    calibrator_name: str = "platt"
    # One fitted calibrator parameter set per class (one-vs-rest).
    calibrator_params: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    dataset_hash: str = ""
    n_samples: int = 0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: str = ""

    def __post_init__(self):
        if not self.name:
            raise CalibrationError("profile needs a name")
        if not self.version:
            raise CalibrationError("profile needs a version")
        # Validate the calibrator name early.
        CalibratorRegistry.get(self.calibrator_name)

    @property
    def classes(self) -> List[str]:
        return sorted(self.calibrator_params.keys())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CalibrationProfile":
        return cls(
            name=d["name"],
            version=d.get("version", "1.0.0"),
            backend_name=d.get("backend_name", ""),
            model_name=d.get("model_name", ""),
            model_version=d.get("model_version", ""),
            calibrator_name=d.get("calibrator_name", "platt"),
            calibrator_params=dict(d.get("calibrator_params", {})),
            metrics=dict(d.get("metrics", {})),
            dataset_hash=d.get("dataset_hash", ""),
            n_samples=int(d.get("n_samples", 0)),
            created_at=d.get("created_at",
                             datetime.now(timezone.utc).isoformat()),
            notes=d.get("notes", ""),
        )

    @classmethod
    def from_json(cls, text: str) -> "CalibrationProfile":
        return cls.from_dict(json.loads(text))

    def build_calibrators(self) -> Dict[str, Calibrator]:
        """Rebuild the fitted per-class calibrators from stored params."""
        return {
            cls_name: CalibratorRegistry.build(self.calibrator_name, params)
            for cls_name, params in self.calibrator_params.items()
        }

    def qualified_name(self) -> str:
        return f"{self.name}@{self.version}"


class CalibrationProfileStore:
    """Disk-backed store for calibration profiles.

    Layout: ``<root>/<name>/<version>.json``.  Weights are never stored
    here — only the calibrator parameters and provenance.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str, version: str) -> Path:
        return self.root / name / f"{version}.json"

    def save(self, profile: CalibrationProfile) -> Path:
        path = self._path(profile.name, profile.version)
        if path.exists():
            raise HugrGateError(
                f"calibration profile {profile.qualified_name()} already "
                f"stored; bump the version")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(profile.to_json())
        return path

    def get(self, name: str,
            version: Optional[str] = None) -> CalibrationProfile:
        if version is None:
            version = self.latest_version(name)
        path = self._path(name, version)
        if not path.is_file():
            raise HugrGateError(
                f"no calibration profile {name}@{version}")
        return CalibrationProfile.from_json(path.read_text())

    def list_versions(self, name: str) -> List[str]:
        ndir = self.root / name
        if not ndir.is_dir():
            return []
        return sorted(p.stem for p in ndir.glob("*.json"))

    def latest_version(self, name: str) -> str:
        versions = self.list_versions(name)
        if not versions:
            raise HugrGateError(f"no stored profiles named {name!r}")
        return versions[-1]

    def list_profiles(self) -> List[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_dir())


class CalibratedBackend(Backend):
    """Wraps a classifier backend with a fitted calibration profile.

    The inner backend must expose ``predict_proba_dict(state)`` (all
    HugrGate sklearn backends do).  Each class probability is passed through
    its one-vs-rest calibrator, the distribution is renormalized, and
    ``result.calibration_profile`` is stamped with the profile name.
    """

    def __init__(self, inner: Backend, profile: CalibrationProfile,
                 calibrators: Optional[Dict[str, Calibrator]] = None):
        if not hasattr(inner, "predict_proba_dict"):
            raise CalibrationError(
                f"inner backend {inner.name!r} has no predict_proba_dict; "
                f"CalibratedBackend needs a probabilistic classifier")
        self._inner = inner
        self._profile = profile
        self._calibrators = (calibrators if calibrators is not None
                             else profile.build_calibrators())
        self.name = f"{inner.name}+calibrated"
        self.is_remote = inner.is_remote

    @property
    def inner(self) -> Backend:
        return self._inner

    @property
    def profile(self) -> CalibrationProfile:
        return self._profile

    def capabilities(self) -> Dict[str, Any]:
        caps = self._inner.capabilities()
        caps["calibrated"] = True
        caps["calibration_profile"] = self._profile.qualified_name()
        return caps

    def supports(self, spec: DecisionSpec) -> bool:
        return self._inner.supports(spec)

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Optional[Mapping[str, Any]] = None
                 ) -> DecisionResult:
        result = self._inner.evaluate(state, spec, context)
        raw = dict(result.distribution)
        calibrated = {}
        for cls_name, p in raw.items():
            cal = self._calibrators.get(cls_name)
            calibrated[cls_name] = cal.calibrate(p) if cal else p
        total = sum(calibrated.values())
        if total <= 0:
            n = len(calibrated)
            calibrated = {k: 1.0 / n for k in calibrated}
        else:
            calibrated = {k: v / total for k, v in calibrated.items()}
        value = max(calibrated, key=lambda k: calibrated[k])
        probability = calibrated[value]
        result.distribution = calibrated
        result.value = value
        result.probability = probability
        result.uncertainty = max(0.0, 1.0 - probability)
        result.calibration_profile = self._profile.qualified_name()
        result.metadata["calibration"] = {
            "profile": self._profile.qualified_name(),
            "calibrator": self._profile.calibrator_name,
            "metrics": dict(self._profile.metrics),
        }
        return result

    def health(self) -> Dict[str, Any]:
        h = self._inner.health()
        h["calibration_profile"] = self._profile.qualified_name()
        return h

    def calibration_info(self) -> Dict[str, Any]:
        return {
            "calibrated": True,
            "profile": self._profile.qualified_name(),
            "calibrator": self._profile.calibrator_name,
            "metrics": dict(self._profile.metrics),
            "dataset_hash": self._profile.dataset_hash,
        }
