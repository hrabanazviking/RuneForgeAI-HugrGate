"""Prompt / data minimization. Slice 236.

Send the least data that still answers the question. This module
provides two mechanisms:

- :func:`minimize_state` — project a state mapping down to an
  explicit keep-list (top-level names or dotted paths); everything
  else is dropped. Nested-aware, non-mutating.
- :class:`MinimizationPolicy` — per-backend keep-lists; backends
  declare the fields they actually need and every outbound payload
  is projected before compilation.
- :class:`PromptMinimizer` — renders the minimized state into a
  compact prompt string under a character budget, so prompt
  construction itself can't smuggle undeclared fields.

A backend with no declared keep-list passes state through unchanged
(documented): minimization is only as good as the declarations, so
declare them.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "MinimizationPolicy",
    "MinimizationReport",
    "PromptMinimizer",
    "minimize_state",
]


def _get_path(state: Mapping[str, Any], parts: tuple[str, ...]) -> Any:
    node: Any = state
    for part in parts:
        if not isinstance(node, Mapping) or part not in node:
            raise KeyError(".".join(parts))
        node = node[part]
    return node


def _set_path(state: dict[str, Any], parts: tuple[str, ...],
              value: Any) -> None:
    node = state
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


@dataclass
class MinimizationReport:
    """What minimization kept and dropped."""

    kept: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    backend: str = ""


def minimize_state(state: Mapping[str, Any],
                   keep: Collection[str],
                   backend: str = "") -> \
        tuple[dict[str, Any], MinimizationReport]:
    """Project ``state`` down to ``keep`` (names or dotted paths).

    Returns ``(minimized, report)``. Fields in ``keep`` that are
    absent are ignored; everything not kept is dropped. The input is
    never mutated.
    """
    keep_paths = [tuple(str(k).split(".")) for k in keep]
    out: dict[str, Any] = {}
    kept: list[str] = []
    for parts in keep_paths:
        try:
            value = _get_path(state, parts)
        except KeyError:
            continue
        _set_path(out, parts, copy.deepcopy(value))
        kept.append(".".join(parts))

    def leaf_paths(node: Any, prefix: str) -> list[str]:
        paths: list[str] = []
        if isinstance(node, Mapping):
            for key, value in node.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                if isinstance(value, Mapping):
                    paths.extend(leaf_paths(value, path))
                else:
                    paths.append(path)
        return paths

    kept_set = set(kept)
    dropped = sorted(p for p in leaf_paths(state, "")
                     if not any(p == k or p.startswith(k + ".")
                                for k in kept_set))
    return out, MinimizationReport(kept=sorted(kept_set),
                                   dropped=dropped, backend=backend)


class MinimizationPolicy:
    """Per-backend keep-lists for outbound data minimization."""

    def __init__(self, keep_lists: Mapping[str, Collection[str]] | None = None,
                 default_keep: Collection[str] | None = None):
        self._keep_lists = {str(n): [str(k) for k in keep]
                            for n, keep in (keep_lists or {}).items()}
        self._default_keep = \
            [str(k) for k in default_keep] if default_keep else None

    def keep_for(self, backend_name: str) -> list[str] | None:
        """Keep-list for a backend, or the default, or None."""
        if backend_name in self._keep_lists:
            return list(self._keep_lists[backend_name])
        return list(self._default_keep) if self._default_keep else None

    def declare(self, backend_name: str,
                keep: Collection[str]) -> None:
        """Declare (or replace) a backend's keep-list."""
        self._keep_lists[str(backend_name)] = [str(k) for k in keep]

    def minimize(self, state: Mapping[str, Any],
                 backend_name: str) -> \
            tuple[dict[str, Any], MinimizationReport]:
        """Minimize ``state`` for a backend.

        Backends without a declared keep-list (and no default) pass
        through unchanged — documented, and reported as such.
        """
        keep = self.keep_for(backend_name)
        if keep is None:
            return copy.deepcopy(dict(state)), MinimizationReport(
                kept=[], dropped=[], backend=backend_name)
        return minimize_state(state, keep, backend=backend_name)

    def to_dict(self) -> dict[str, Any]:
        return {"keep_lists": {n: list(k)
                               for n, k in self._keep_lists.items()},
                "default_keep": self._default_keep}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MinimizationPolicy:
        return cls(keep_lists=data.get("keep_lists"),
                   default_keep=data.get("default_keep"))


class PromptMinimizer:
    """Renders minimized state into a compact, budgeted prompt string.

    Parameters
    ----------
    max_chars:
        Hard budget for the rendered prompt body. Fields are emitted
        in keep-list order; the first field that would overflow is
        skipped (with the skip recorded), never truncated mid-value.
    """

    def __init__(self, max_chars: int = 4000):
        if max_chars <= 0:
            raise ValueError("max_chars must be > 0")
        self.max_chars = max_chars

    def render(self, state: Mapping[str, Any],
               keep: Collection[str]) -> tuple[str, MinimizationReport]:
        """Minimize then render as compact JSON lines under budget."""
        minimized, report = minimize_state(state, keep)
        lines: list[str] = []
        used = 0
        skipped: list[str] = []
        for key in sorted(minimized):
            line = json.dumps({key: minimized[key]}, sort_keys=True,
                              default=str)
            if used + len(line) > self.max_chars:
                skipped.append(key)
                continue
            lines.append(line)
            used += len(line)
        report.dropped.extend(f"prompt-budget:{k}" for k in skipped)
        return "\n".join(lines), report
