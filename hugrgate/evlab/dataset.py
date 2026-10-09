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
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import DatasetError

__all__ = [
    "COLUMN_TYPES",
    "ColumnSpec",
    "DatasetManifest",
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
            extra=dict(data.get("extra", {})),
        )
