"""Field-level sensitivity labels. Slice 227.

The privacy-class ladder (slice 226) classifies a whole *decision*.
This module classifies the *fields inside the state*: each field gets
a :class:`Sensitivity` level, consumers get a clearance, and
:func:`filter_by_clearance` drops everything above it. Fields can
also be marked *local-only* — they may be processed in-process but
must never be compiled into a remote payload (enforced in slice 231).

Labels support dotted paths (``"user.ssn"``) for nested mappings; a
label on a parent (``"user"``) covers its children unless a more
specific dotted label overrides it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import IntEnum
from typing import Any

__all__ = [
    "FieldLabels",
    "Sensitivity",
    "filter_by_clearance",
]


class Sensitivity(IntEnum):
    """Ordered sensitivity of a single field (higher = more sensitive)."""

    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    SECRET = 3

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name.lower()


def _split_path(field: str) -> tuple[str, ...]:
    return tuple(field.split("."))


def _get_path(state: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    node: Any = state
    for part in path:
        if not isinstance(node, Mapping) or part not in node:
            raise KeyError(part)
        node = node[part]
    return node


def _set_path(state: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    node = state
    for part in path[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[path[-1]] = value


class FieldLabels:
    """Sensitivity labels for state fields.

    Parameters
    ----------
    labels:
        Mapping of field name (or dotted path for nested fields) to
        :class:`Sensitivity`. Unlisted fields get ``default``.
    default:
        Sensitivity for unlabeled fields.
    local_only:
        Field names/paths that must never leave the process, even when
        their sensitivity level would otherwise permit it. Enforced by
        the remote payload compiler (slice 231).
    """

    def __init__(self,
                 labels: Mapping[str, Sensitivity | str | int] | None = None,
                 default: Sensitivity | str | int = Sensitivity.PUBLIC,
                 local_only: Iterable[str] | None = None):
        self._labels: dict[str, Sensitivity] = {}
        for field, level in (labels or {}).items():
            self._labels[str(field)] = self._coerce(level)
        self.default = self._coerce(default)
        self.local_only = frozenset(str(f) for f in (local_only or ()))

    @staticmethod
    def _coerce(level: Sensitivity | str | int) -> Sensitivity:
        if isinstance(level, Sensitivity):
            return level
        if isinstance(level, str):
            try:
                return Sensitivity[level.upper()]
            except KeyError:
                raise ValueError(
                    f"unknown sensitivity: {level!r}; expected one of "
                    f"{[s.name.lower() for s in Sensitivity]}") from None
        return Sensitivity(int(level))

    def label(self, field: str) -> Sensitivity:
        """Most specific label for ``field`` (dotted path aware).

        Exact dotted match wins; otherwise the longest labeled parent
        prefix wins; otherwise ``default``.
        """
        parts = _split_path(field)
        for i in range(len(parts), 0, -1):
            prefix = ".".join(parts[:i])
            if prefix in self._labels:
                return self._labels[prefix]
        return self.default

    def is_local_only(self, field: str) -> bool:
        """True when the field (or any parent path) is local-only."""
        parts = _split_path(field)
        for i in range(len(parts), 0, -1):
            if ".".join(parts[:i]) in self.local_only:
                return True
        return False

    def label_state(self, state: Mapping[str, Any]) -> dict[str, Sensitivity]:
        """Label every leaf of a (possibly nested) state mapping."""
        out: dict[str, Sensitivity] = {}

        def walk(node: Any, prefix: str) -> None:
            if isinstance(node, Mapping):
                for key, value in node.items():
                    path = f"{prefix}.{key}" if prefix else str(key)
                    walk(value, path)
            else:
                out[prefix] = self.label(prefix)

        walk(state, "")
        return out

    def fields_at_or_above(self, level: Sensitivity | str | int,
                           state: Mapping[str, Any] | None = None) -> list[str]:
        """Labeled field paths at or above ``level``.

        When ``state`` is given, only paths present in it are returned;
        otherwise all explicitly labeled paths are returned.
        """
        threshold = self._coerce(level)
        if state is None:
            return sorted(f for f, lvl in self._labels.items()
                          if lvl >= threshold)
        return sorted(f for f, lvl in self.label_state(state).items()
                      if lvl >= threshold)

    def to_dict(self) -> dict[str, Any]:
        return {
            "labels": {f: lvl.name.lower()
                       for f, lvl in self._labels.items()},
            "default": self.default.name.lower(),
            "local_only": sorted(self.local_only),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FieldLabels:
        return cls(labels=data.get("labels", {}),
                   default=data.get("default", "public"),
                   local_only=data.get("local_only", ()))

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (f"FieldLabels({len(self._labels)} labels, "
                f"default={self.default}, local_only={len(self.local_only)})")


def filter_by_clearance(state: Mapping[str, Any], labels: FieldLabels,
                        clearance: Sensitivity | str | int,
                        drop_local_only: bool = True) -> dict[str, Any]:
    """Return a copy of ``state`` with fields above ``clearance`` removed.

    Nested mappings are filtered recursively; empty mappings left
    behind are pruned. Local-only fields are dropped when
    ``drop_local_only`` is True (remote consumers).
    """
    allowed = FieldLabels._coerce(clearance)
    labeled = labels.label_state(state)
    out: dict[str, Any] = {}
    for path in sorted(labeled):
        if labeled[path] > allowed:
            continue
        if drop_local_only and labels.is_local_only(path):
            continue
        _set_path(out, _split_path(path), _get_path(state, _split_path(path)))
    return out
