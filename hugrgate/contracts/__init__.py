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
from hugrgate.contracts import negotiation

__all__ = [
    "SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "CONTRACT_KINDS",
    "DecisionContract",
    "contract_from_dict",
    "is_supported_version",
    "register_kind",
    "negotiation",
]
