"""Local-only field enforcement. Slice 231.

Slice 227 lets operators *mark* fields local-only; this module
*enforces* the marking. :class:`LocalOnlyPolicy` inspects an
outbound state against :class:`~hugrgate.privacy_labels.FieldLabels`
and guarantees no local-only field reaches a remote destination:

- strip mode (default): local-only fields are removed from the
  outbound copy and reported;
- strict mode: the mere presence of a local-only field in a
  remote-bound payload raises :class:`LocalOnlyViolation` — a hard
  guarantee for callers that must never silently drop data.

In-process (local backend) flows are untouched: local-only means
"never leaves the process", not "never used".
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.backend import Backend
from hugrgate.errors import LocalOnlyViolation
from hugrgate.privacy_labels import FieldLabels

__all__ = [
    "LocalOnlyPolicy",
    "LocalOnlyResult",
    "enforce_local_only",
]


@dataclass
class LocalOnlyResult:
    """Outcome of enforcing local-only marking on an outbound state."""

    state: dict[str, Any]
    stripped: list[str] = field(default_factory=list)
    remote: bool = False

    @property
    def clean(self) -> bool:
        """True when no local-only field was present."""
        return not self.stripped


def _delete_path(state: dict[str, Any], parts: tuple[str, ...]) -> bool:
    """Delete a dotted path from a nested dict; prune emptied parents."""
    node = state
    trail: list[tuple[dict[str, Any], str]] = []
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return False
        trail.append((node, part))
        node = node[part]
    parent, key = trail[-1]
    del parent[key]
    # Prune emptied ancestor mappings (but never the root itself).
    for parent, key in reversed(trail[:-1]):
        child = parent[key]
        if isinstance(child, dict) and not child:
            del parent[key]
        else:
            break
    return True


def _present_local_only(state: Mapping[str, Any],
                        labels: FieldLabels) -> list[str]:
    """Local-only field paths actually present in ``state``."""
    return sorted(p for p in labels.label_state(state)
                  if labels.is_local_only(p))


class LocalOnlyPolicy:
    """Enforces local-only field marking on outbound state.

    Parameters
    ----------
    strict:
        When True, raise :class:`LocalOnlyViolation` instead of
        stripping. Use for paths where silent data loss is worse
        than a hard failure (e.g. audited pipelines).
    """

    def __init__(self, strict: bool = False):
        self.strict = strict

    def enforce(self, state: Mapping[str, Any], labels: FieldLabels,
                *, remote: bool) -> LocalOnlyResult:
        """Enforce local-only marking.

        Local destinations pass through untouched. Remote
        destinations get local-only fields stripped (or a raise in
        strict mode). The input is never mutated.
        """
        present = _present_local_only(state, labels)
        if not remote or not present:
            return LocalOnlyResult(state=copy.deepcopy(dict(state)),
                                   stripped=[], remote=remote)
        if self.strict:
            raise LocalOnlyViolation(
                f"local-only field(s) {present} would leave the process",
                fields=present)
        stripped = copy.deepcopy(dict(state))
        for path in present:
            _delete_path(stripped, tuple(path.split(".")))
        return LocalOnlyResult(state=stripped, stripped=present,
                               remote=remote)

    def enforce_for_backend(self, state: Mapping[str, Any],
                            labels: FieldLabels,
                            backend: Backend) -> LocalOnlyResult:
        """Enforce based on a backend's remoteness."""
        return self.enforce(state, labels, remote=backend.is_remote)

    def to_dict(self) -> dict[str, Any]:
        return {"strict": self.strict}


def enforce_local_only(state: Mapping[str, Any], labels: FieldLabels,
                       *, remote: bool,
                       strict: bool = False) -> LocalOnlyResult:
    """One-shot enforcement (see :class:`LocalOnlyPolicy`)."""
    return LocalOnlyPolicy(strict=strict).enforce(state, labels,
                                                  remote=remote)
