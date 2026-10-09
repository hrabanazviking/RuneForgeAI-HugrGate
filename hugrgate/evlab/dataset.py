"""Dataset manifests, versioning, and provenance. Slices 352-354.

What exists (inspected): :func:`hugrgate.bench.dataset_fingerprint`
gives a bare sha16 over items.  There is no manifest standard — no
schema declaration, no license/size metadata, no item validation, no
versioning, no provenance chain.  This module is the lab's dataset
contract:

- Slice 352 (this slice): :class:`DatasetManifest` — the manifest
  standard: name, version, column schema, license, fingerprint, item
  validation against the schema, and a bridge
  (:meth:`DatasetManifest.to_bench_dataset`) into the v1 bench dataset
  shape consumed by :class:`hugrgate.evlab.api.Experiment`.
- Slice 353: :class:`DatasetVersion` + :class:`DatasetRegistry` —
  version parsing, bumping, compatibility, registry resolution.
- Slice 354: :class:`DatasetProvenance` — source, acquisition, and
  transform-chain provenance.

Item validation is strict and loud: :meth:`DatasetManifest.validate`
raises :class:`DatasetError` with the full issue list in
``details["issues"]``.  A non-raising :meth:`DatasetManifest.check`
exists for tooling that wants to render issues itself.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import total_ordering
from typing import Any

from hugrgate.errors import DatasetError

__all__ = [
    "ACQUISITIONS",
    "COLUMN_TYPES",
    "ColumnSpec",
    "DatasetManifest",
    "DatasetProvenance",
    "DatasetRegistry",
    "DatasetVersion",
    "TransformStep",
]

#: Declared column value types understood by the manifest validator.
COLUMN_TYPES = (
    "string",
    "number",
    "boolean",
    "categorical",
    "list",
    "mapping",
    "any",
)


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


@dataclass
class ColumnSpec:
    """One declared column of a dataset's items.

    ``type`` is one of :data:`COLUMN_TYPES`.  ``options`` constrains
    ``"categorical"`` columns (and is ignored otherwise).
    """

    name: str
    type: str = "any"
    required: bool = True
    options: list[str] | None = None

    def validate_decl(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise DatasetError("column name must be a non-empty string")
        if self.type not in COLUMN_TYPES:
            raise DatasetError(
                f"unknown column type {self.type!r}; "
                f"expected one of {list(COLUMN_TYPES)}",
                column=self.name,
            )
        if self.type == "categorical":
            if not self.options or not all(
                isinstance(o, str) for o in self.options
            ):
                raise DatasetError(
                    "categorical columns need a non-empty options list "
                    "of strings",
                    column=self.name,
                )

    def check_value(self, value: Any) -> str | None:
        """Return an issue string, or None when the value is valid."""
        if value is None:
            return None  # missing/None handled by the required check
        kind = self.type
        if kind == "any":
            return None
        if kind == "string":
            return None if isinstance(value, str) else "expected string"
        if kind == "boolean":
            return None if isinstance(value, bool) else "expected boolean"
        if kind == "number":
            # bool is a subclass of int: reject it explicitly.
            ok = isinstance(value, (int, float)) and not isinstance(
                value, bool
            )
            return None if ok else "expected number"
        if kind == "list":
            return None if isinstance(value, list) else "expected list"
        if kind == "mapping":
            return None if isinstance(value, Mapping) else "expected mapping"
        if kind == "categorical":
            if not isinstance(value, str):
                return "expected categorical string"
            if self.options is not None and value not in self.options:
                return f"{value!r} not in options {self.options}"
            return None
        return f"unknown column type {kind!r}"  # pragma: no cover

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "options": list(self.options) if self.options else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ColumnSpec:
        return cls(
            name=data["name"],
            type=data.get("type", "any"),
            required=data.get("required", True),
            options=data.get("options"),
        )


def fingerprint_items(items: list[Mapping[str, Any]]) -> str:
    """Stable sha256 over canonicalized items (reproducibility anchor)."""
    payload = json.dumps(items, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class DatasetManifest:
    """The lab's dataset contract (slice 352).

    A manifest describes a dataset's identity (name, version,
    fingerprint), its item schema (columns), and its handling metadata
    (license, sensitivity, spec).  The items themselves travel
    separately; :meth:`to_bench_dataset` rejoins them into the v1 bench
    dataset shape.
    """

    name: str
    version: str
    columns: list[ColumnSpec] = field(default_factory=list)
    description: str = ""
    license: str = "unknown"
    spec: dict[str, Any] = field(default_factory=dict)
    sensitivity: str = "public"
    fingerprint: str = ""
    created_at: str = ""
    provenance: DatasetProvenance | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _utc_now()

    def validate_decl(self) -> None:
        """Validate the manifest declaration itself."""
        if not self.name or not isinstance(self.name, str):
            raise DatasetError("manifest name must be a non-empty string")
        if not self.version or not isinstance(self.version, str):
            raise DatasetError("manifest version must be a non-empty string")
        if self.sensitivity not in ("public", "restricted"):
            raise DatasetError(
                f"unknown sensitivity {self.sensitivity!r}; "
                "expected 'public' or 'restricted'"
            )
        seen: set[str] = set()
        for col in self.columns:
            col.validate_decl()
            if col.name in seen:
                raise DatasetError(
                    f"duplicate column declaration: {col.name!r}"
                )
            seen.add(col.name)
        if self.fingerprint and (
            len(self.fingerprint) != 64
            or any(c not in "0123456789abcdef"
                   for c in self.fingerprint)
        ):
            raise DatasetError("fingerprint must be a sha256 hex digest")
        if self.provenance is not None:
            if not isinstance(self.provenance, DatasetProvenance):
                raise DatasetError("provenance must be a DatasetProvenance")
            self.provenance.validate()

    def check(self, items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Return the list of schema issues without raising."""
        issues: list[dict[str, Any]] = []
        for idx, item in enumerate(items):
            if not isinstance(item, Mapping):
                issues.append({"item": idx, "issue": "not a mapping"})
                continue
            for col in self.columns:
                if col.name not in item or item[col.name] is None:
                    if col.required:
                        issues.append({
                            "item": idx,
                            "column": col.name,
                            "issue": "missing required column",
                        })
                    continue
                problem = col.check_value(item[col.name])
                if problem is not None:
                    issues.append({
                        "item": idx,
                        "column": col.name,
                        "issue": problem,
                    })
        return issues

    def validate(self, items: list[Mapping[str, Any]]) -> None:
        """Validate items against the schema; raise on any issue."""
        self.validate_decl()
        issues = self.check(items)
        if issues:
            raise DatasetError(
                f"{len(issues)} schema issue(s) in dataset "
                f"{self.name!r} v{self.version}",
                issues=issues[:25],  # details stay bounded; full list via check()
                n_issues=len(issues),
            )

    def seal(self, items: list[Mapping[str, Any]]) -> DatasetManifest:
        """Validate items and stamp the fingerprint; returns a copy."""
        self.validate(items)
        sealed = copy.deepcopy(self)
        sealed.fingerprint = fingerprint_items(items)
        return sealed

    def verify(self, items: list[Mapping[str, Any]]) -> None:
        """Re-validate items *and* the fingerprint; raise on mismatch."""
        self.validate(items)
        if not self.fingerprint:
            raise DatasetError(
                f"manifest {self.name!r} v{self.version} is not sealed "
                "(no fingerprint); seal it before verifying"
            )
        actual = fingerprint_items(items)
        if actual != self.fingerprint:
            raise DatasetError(
                f"fingerprint mismatch for {self.name!r} v{self.version}: "
                "items changed since sealing",
                expected=self.fingerprint,
                actual=actual,
            )
        if self.provenance is not None and self.provenance.steps:
            self.provenance.verify(self.fingerprint)

    def bumped(self, kind: str = "patch") -> DatasetManifest:
        """Copy with a bumped version (slice 353).

        The copy's fingerprint is cleared — it must be re-sealed
        against the (possibly changed) items.  ``kind`` is one of
        ``"major"``, ``"minor"``, ``"patch"``.
        """
        version = DatasetVersion.parse(self.version)
        bump = {
            "major": version.bump_major,
            "minor": version.bump_minor,
            "patch": version.bump_patch,
        }.get(kind)
        if bump is None:
            raise DatasetError(
                f"unknown bump kind {kind!r}; "
                "expected 'major', 'minor', or 'patch'"
            )
        nxt = copy.deepcopy(self)
        nxt.version = str(bump())
        nxt.fingerprint = ""
        nxt.created_at = _utc_now()
        return nxt

    def to_bench_dataset(
        self, items: list[Mapping[str, Any]]
    ) -> dict[str, Any]:
        """Rejoin manifest + items into the v1 bench dataset shape."""
        self.verify(items)
        dataset: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "spec": dict(self.spec),
            "items": [dict(i) for i in items],
        }
        if self.sensitivity == "restricted":
            dataset["sensitivity"] = "restricted"
        return dataset

    @classmethod
    def from_bench_dataset(
        cls,
        dataset: Mapping[str, Any],
        columns: list[ColumnSpec] | None = None,
    ) -> DatasetManifest:
        """Adopt a v1 bench dataset mapping into a manifest.

        When ``columns`` is omitted, a permissive schema is inferred:
        ``state`` (mapping, required) and ``expected`` (any, optional).
        """
        items = list(dataset.get("items", []))
        inferred = columns if columns is not None else [
            ColumnSpec(name="state", type="mapping", required=True),
            ColumnSpec(name="expected", type="any", required=False),
        ]
        manifest = cls(
            name=str(dataset.get("name", "unnamed")),
            version=str(dataset.get("version", "0.0.0")),
            columns=inferred,
            spec=dict(dataset.get("spec", {})),
            sensitivity=str(dataset.get("sensitivity", "public")),
        )
        manifest.validate_decl()
        # Seal against the current items so the manifest is anchored.
        return manifest.seal(items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "columns": [c.to_dict() for c in self.columns],
            "description": self.description,
            "license": self.license,
            "spec": dict(self.spec),
            "sensitivity": self.sensitivity,
            "fingerprint": self.fingerprint,
            "created_at": self.created_at,
            "provenance": (self.provenance.to_dict()
                           if self.provenance else None),
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DatasetManifest:
        return cls(
            name=data["name"],
            version=data["version"],
            columns=[ColumnSpec.from_dict(c)
                     for c in data.get("columns", [])],
            description=data.get("description", ""),
            license=data.get("license", "unknown"),
            spec=dict(data.get("spec", {})),
            sensitivity=data.get("sensitivity", "public"),
            fingerprint=data.get("fingerprint", ""),
            created_at=data.get("created_at", ""),
            provenance=(DatasetProvenance.from_dict(data["provenance"])
                        if data.get("provenance") else None),
            extra=dict(data.get("extra", {})),
        )


# ---------------------------------------------------------------------------
# Slice 353 — dataset versioning
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$"
)


@total_ordering
@dataclass(frozen=True)
class DatasetVersion:
    """Semantic version for datasets (slice 353).

    ``major`` bumps mark breaking changes (removed columns, type
    narrowing, redefined semantics); ``minor``/``patch`` are
    backward-compatible.  Ordering follows semver: a prerelease sorts
    below its release; build metadata is ignored for precedence.
    """

    major: int
    minor: int
    patch: int
    prerelease: str = ""
    build: str = ""

    @classmethod
    def parse(cls, text: str) -> DatasetVersion:
        """Parse ``MAJOR.MINOR.PATCH[-pre][+build]``; DatasetError on bad."""
        if not isinstance(text, str):
            raise DatasetError(
                f"version must be a string, got {type(text).__name__}"
            )
        match = _VERSION_RE.match(text.strip())
        if not match:
            raise DatasetError(
                f"invalid dataset version {text!r}; expected "
                "MAJOR.MINOR.PATCH[-prerelease][+build]",
                version=text,
            )
        major, minor, patch, pre, build = match.groups()
        return cls(int(major), int(minor), int(patch), pre or "",
                   build or "")

    @classmethod
    def parse_partial(cls, text: str) -> DatasetVersion:
        """Parse ``MAJOR[.MINOR[.PATCH]]`` for caret constraints.

        Missing components are zero-filled: ``"^1.2"`` means
        ``>=1.2.0, <2.0.0``.
        """
        if not isinstance(text, str):
            raise DatasetError(
                f"version constraint must be a string, got "
                f"{type(text).__name__}"
            )
        parts = text.strip().split(".")
        if not 1 <= len(parts) <= 3 or not all(
            p.isdigit() for p in parts
        ):
            raise DatasetError(
                f"invalid version constraint {text!r}; expected "
                "MAJOR[.MINOR[.PATCH]]",
                constraint=text,
            )
        nums = [int(p) for p in parts] + [0] * (3 - len(parts))
        return cls(nums[0], nums[1], nums[2])

    def bump_major(self) -> DatasetVersion:
        return DatasetVersion(self.major + 1, 0, 0)

    def bump_minor(self) -> DatasetVersion:
        return DatasetVersion(self.major, self.minor + 1, 0)

    def bump_patch(self) -> DatasetVersion:
        return DatasetVersion(self.major, self.minor, self.patch + 1)

    def is_prerelease(self) -> bool:
        return bool(self.prerelease)

    def is_compatible_with(self, other: DatasetVersion) -> bool:
        """Same-major compatibility (semver ^ semantics)."""
        return self.major == other.major

    def _precedence(self) -> tuple:
        # Release (no prerelease) sorts above any prerelease of the same
        # triple; prereleases order lexicographically by identifier.
        pre: tuple = (1,) if not self.prerelease else (0, self.prerelease)
        return (self.major, self.minor, self.patch, pre)

    def __lt__(self, other: DatasetVersion) -> bool:
        if not isinstance(other, DatasetVersion):
            return NotImplemented
        return self._precedence() < other._precedence()

    def __str__(self) -> str:
        text = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            text += f"-{self.prerelease}"
        if self.build:
            text += f"+{self.build}"
        return text


class DatasetRegistry:
    """Versioned store of dataset manifests (slice 353).

    Register sealed manifests; resolve by exact version, ``"latest"``,
    or caret constraint (``"^1.2"`` → newest compatible 1.x); diff
    versions for schema drift; check backward compatibility.
    """

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], DatasetManifest] = {}

    def register(self, manifest: DatasetManifest) -> DatasetManifest:
        manifest.validate_decl()
        key = (manifest.name, manifest.version)
        if key in self._store:
            raise DatasetError(
                f"dataset {manifest.name!r} version {manifest.version!r} "
                "is already registered",
                name=manifest.name, version=manifest.version,
            )
        # Registry entries must be parseable versions.
        DatasetVersion.parse(manifest.version)
        self._store[key] = manifest
        return manifest

    def versions(self, name: str) -> list[str]:
        """All registered versions of ``name``, oldest first."""
        found = [DatasetVersion.parse(v)
                 for (n, v) in self._store if n == name]
        return [str(v) for v in sorted(found)]

    def get(self, name: str, version: str) -> DatasetManifest:
        try:
            return self._store[(name, version)]
        except KeyError:
            raise DatasetError(
                f"unknown dataset {name!r} version {version!r}; "
                f"known: {self.versions(name) or 'none'}",
                name=name, version=version,
            ) from None

    def latest(self, name: str,
               include_prerelease: bool = False) -> DatasetManifest:
        """Newest registered version (releases preferred by default)."""
        candidates = [
            m for (n, _), m in self._store.items() if n == name
        ]
        if not candidates:
            raise DatasetError(f"unknown dataset {name!r}", name=name)
        if not include_prerelease:
            releases = [m for m in candidates
                        if not DatasetVersion.parse(m.version).is_prerelease()]
            if releases:
                candidates = releases
        return max(candidates,
                   key=lambda m: DatasetVersion.parse(m.version))

    def resolve(self, name: str, constraint: str = "latest") -> DatasetManifest:
        """Resolve ``name`` under ``constraint``.

        Constraints: ``"latest"``, an exact version (``"1.2.3"``), or a
        caret constraint (``"^1.2"`` → newest 1.x >= 1.2.0).
        """
        if constraint == "latest":
            return self.latest(name)
        if constraint.startswith("^"):
            base = DatasetVersion.parse_partial(constraint[1:])
            compatible = [
                m for (n, _), m in self._store.items()
                if n == name
                and DatasetVersion.parse(m.version).is_compatible_with(base)
                and DatasetVersion.parse(m.version) >= base
            ]
            if not compatible:
                raise DatasetError(
                    f"no version of {name!r} satisfies {constraint!r}",
                    name=name, constraint=constraint,
                )
            return max(compatible,
                       key=lambda m: DatasetVersion.parse(m.version))
        return self.get(name, str(DatasetVersion.parse(constraint)))

    @staticmethod
    def diff(old: DatasetManifest, new: DatasetManifest) -> dict[str, Any]:
        """Schema/content drift between two manifests of one dataset."""
        if old.name != new.name:
            raise DatasetError(
                f"cannot diff different datasets: {old.name!r} vs {new.name!r}"
            )
        old_cols = {c.name: c for c in old.columns}
        new_cols = {c.name: c for c in new.columns}
        added = sorted(set(new_cols) - set(old_cols))
        removed = sorted(set(old_cols) - set(new_cols))
        changed = sorted(
            name for name in set(old_cols) & set(new_cols)
            if old_cols[name].to_dict() != new_cols[name].to_dict()
        )
        return {
            "dataset": old.name,
            "from_version": old.version,
            "to_version": new.version,
            "added_columns": added,
            "removed_columns": removed,
            "changed_columns": changed,
            "fingerprint_changed": old.fingerprint != new.fingerprint,
            "sensitivity_changed": old.sensitivity != new.sensitivity,
            "breaking": bool(removed or changed),
        }

    @staticmethod
    def check_compatible(old: DatasetManifest,
                         new: DatasetManifest) -> bool:
        """True when ``new`` is a safe replacement for ``old``.

        Requires: same major version, no removed columns, no changed
        column declarations (type narrowing included).
        """
        try:
            old_v = DatasetVersion.parse(old.version)
            new_v = DatasetVersion.parse(new.version)
        except DatasetError:
            return False
        if not new_v.is_compatible_with(old_v):
            return False
        drift = DatasetRegistry.diff(old, new)
        return not drift["removed_columns"] and not drift["changed_columns"]


# ---------------------------------------------------------------------------
# Slice 354 — dataset provenance
# ---------------------------------------------------------------------------

#: How a dataset came into being.
ACQUISITIONS = (
    "download",   # fetched from a source_uri
    "generated",  # produced by a tool/pipeline
    "derived",    # transformed from parent dataset(s)
    "synthetic",  # fabricated (fuzzers, scenario builders)
    "manual",     # hand-curated
)


@dataclass
class TransformStep:
    """One link in a dataset's derivation chain (slice 354).

    ``input_fingerprint``/``output_fingerprint`` are item-set sha256
    anchors (see :func:`fingerprint_items`): the chain is continuous
    when every step's input matches the previous step's output (or the
    parent fingerprint for the first step).
    """

    name: str
    tool: str = ""
    tool_version: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    input_fingerprint: str = ""
    output_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tool": self.tool,
            "tool_version": self.tool_version,
            "params": dict(self.params),
            "input_fingerprint": self.input_fingerprint,
            "output_fingerprint": self.output_fingerprint,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TransformStep:
        return cls(
            name=data["name"],
            tool=data.get("tool", ""),
            tool_version=data.get("tool_version", ""),
            params=dict(data.get("params", {})),
            input_fingerprint=data.get("input_fingerprint", ""),
            output_fingerprint=data.get("output_fingerprint", ""),
        )


@dataclass
class DatasetProvenance:
    """Where a dataset came from and how it was shaped (slice 354).

    This is *dataset-level* provenance — the complement of
    :mod:`hugrgate.provenance`, which records per-decision lineage.
    The two meet in :class:`hugrgate.evlab.api.RunRecord`, which
    carries the dataset fingerprint that this chain anchors.
    """

    source_uri: str = ""
    acquisition: str = "manual"
    creator: str = ""
    created_at: str = ""
    license: str = "unknown"
    parents: list[dict[str, str]] = field(default_factory=list)
    steps: list[TransformStep] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _utc_now()

    def validate(self) -> None:
        if self.acquisition not in ACQUISITIONS:
            raise DatasetError(
                f"unknown acquisition {self.acquisition!r}; expected one "
                f"of {list(ACQUISITIONS)}"
            )
        if self.acquisition == "download" and not self.source_uri:
            raise DatasetError(
                "acquisition='download' requires a source_uri"
            )
        if self.acquisition == "derived" and not self.parents:
            raise DatasetError(
                "acquisition='derived' requires at least one parent dataset"
            )
        for parent in self.parents:
            if not {"name", "version", "fingerprint"} <= set(parent):
                raise DatasetError(
                    "parent entries need name, version, and fingerprint",
                    parent=parent,
                )
        for step in self.steps:
            if not step.name:
                raise DatasetError("transform steps need a name")

    def add_step(self, step: TransformStep) -> TransformStep:
        """Append a step, auto-linking its input to the chain tip."""
        if self.steps and not step.input_fingerprint:
            step.input_fingerprint = self.steps[-1].output_fingerprint
        self.steps.append(step)
        return step

    @property
    def chain_hash(self) -> str:
        """sha256 over the canonicalized step chain."""
        payload = json.dumps([s.to_dict() for s in self.steps],
                             sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    @property
    def tip_fingerprint(self) -> str | None:
        """Output fingerprint of the last step, if any."""
        return self.steps[-1].output_fingerprint if self.steps else None

    def verify(self, final_fingerprint: str) -> None:
        """Check chain continuity and that the tip anchors ``final``."""
        self.validate()
        previous: str | None = None
        for idx, step in enumerate(self.steps):
            if idx == 0:
                if self.parents:
                    expected_inputs = {
                        p["fingerprint"] for p in self.parents
                    }
                    if (step.input_fingerprint
                            and step.input_fingerprint not in expected_inputs):
                        raise DatasetError(
                            f"step 0 {step.name!r} input does not match "
                            "any parent fingerprint",
                            step=step.name,
                        )
            elif step.input_fingerprint != previous:
                raise DatasetError(
                    f"provenance chain broken at step {idx} {step.name!r}: "
                    "input fingerprint does not match previous output",
                    step=step.name,
                )
            if not step.output_fingerprint:
                raise DatasetError(
                    f"step {idx} {step.name!r} has no output fingerprint",
                    step=step.name,
                )
            previous = step.output_fingerprint
        tip = self.tip_fingerprint
        if tip and tip != final_fingerprint:
            raise DatasetError(
                "provenance tip does not anchor the dataset fingerprint: "
                "the items changed after the recorded transforms",
                tip=tip, dataset_fingerprint=final_fingerprint,
            )

    def summary(self) -> dict[str, Any]:
        """Compact dict for embedding in run records / decision logs."""
        return {
            "acquisition": self.acquisition,
            "source_uri": self.source_uri,
            "creator": self.creator,
            "license": self.license,
            "n_parents": len(self.parents),
            "n_steps": len(self.steps),
            "chain_hash": self.chain_hash,
            "tip_fingerprint": self.tip_fingerprint,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_uri": self.source_uri,
            "acquisition": self.acquisition,
            "creator": self.creator,
            "created_at": self.created_at,
            "license": self.license,
            "parents": [dict(p) for p in self.parents],
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DatasetProvenance:
        return cls(
            source_uri=data.get("source_uri", ""),
            acquisition=data.get("acquisition", "manual"),
            creator=data.get("creator", ""),
            created_at=data.get("created_at", ""),
            license=data.get("license", "unknown"),
            parents=[dict(p) for p in data.get("parents", [])],
            steps=[TransformStep.from_dict(s)
                   for s in data.get("steps", [])],
        )
