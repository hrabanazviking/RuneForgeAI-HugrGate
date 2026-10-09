"""Decision contracts — versioned, self-describing decision specifications.

Campaign II (Gjallarbrú slices 026-050) builds the Contract Engine here,
alongside the v1 :class:`hugrgate.spec.DecisionSpec` which is left
untouched for backward compatibility.
"""

from __future__ import annotations

from hugrgate.contracts.schema import (
    SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    CONTRACT_KINDS,
    DecisionContract,
    contract_from_dict,
    is_supported_version,
    register_kind,
)

__all__ = [
    "SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "CONTRACT_KINDS",
    "DecisionContract",
    "contract_from_dict",
    "is_supported_version",
    "register_kind",
    "negotiation",
    "nested",
    "hierarchy",
    "composite",
    "conditional",
    "crossfield",
    "ordinal",
    "uncertainty",
    "distributions",
    "multilabel",
    "cost",
    "utility",
    "risk",
    "deadlines",
]


def __getattr__(name: str):
    # Lazy submodule access: keeps the eager import graph acyclic
    # (hugrgate.contracts -> hugrgate.contracts would be a self-edge).
    # importlib.import_module is used instead of `from ... import ...`,
    # which would re-enter __getattr__ and recurse forever.
    if name in ("negotiation", "nested", "hierarchy", "composite",
                "conditional", "crossfield", "ordinal", "uncertainty",
                "distributions", "multilabel", "cost", "utility",
                "risk", "deadlines"):
        import importlib
        module = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
