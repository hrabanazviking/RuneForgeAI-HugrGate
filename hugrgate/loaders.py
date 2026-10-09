"""Shared file loaders for the CLI and the inspector.

Gjallarbrú slice 444 (extracted from ``hugrgate.cli``).

``load_spec`` / ``load_state`` / ``load_policy`` used to live in
:mod:`hugrgate.cli`, but the inspector (:mod:`hugrgate.inspect`)
needs them too — and the CLI needs the inspector for
``hugrgate inspect``. Keeping them here breaks that import cycle.
:mod:`hugrgate.cli` re-exports them, so ``hugrgate.cli.load_spec``
keeps working.
"""

from __future__ import annotations

from typing import Any

from hugrgate.policy import DecisionPolicy
from hugrgate.spec import DecisionSpec

__all__ = [
    "load_policy",
    "load_spec",
    "load_state",
]


def _load_doc(path: str) -> Any:
    """Load a JSON or YAML document (YAML is a superset of JSON)."""
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_spec(path: str) -> DecisionSpec:
    doc = _load_doc(path)
    if not isinstance(doc, dict):
        raise ValueError(f"spec file {path} must contain a mapping")
    return DecisionSpec.from_dict(doc)


def load_state(path: str) -> dict[str, Any]:
    doc = _load_doc(path)
    if not isinstance(doc, dict):
        raise ValueError(f"state file {path} must contain a mapping")
    return doc


def load_policy(path: str) -> DecisionPolicy:
    from hugrgate.serde import policy_from_dict
    doc = _load_doc(path)
    if not isinstance(doc, dict):
        raise ValueError(f"policy file {path} must contain a mapping")
    return policy_from_dict(doc)
