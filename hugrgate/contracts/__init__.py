"""Decision contracts — versioned, self-describing decision specifications.

Campaign II (Gjallarbrú slices 026-050) builds the Contract Engine here,
alongside the v1 :class:`hugrgate.spec.DecisionSpec` which is left
untouched for backward compatibility.

All contract submodules are imported eagerly (``import`` form, so the
import graph stays acyclic) so every contract ``kind`` is registered the
moment this package is imported — ``contract_from_dict`` never fails on
an unimported kind.
"""

from __future__ import annotations

import hugrgate.contracts.schema
import hugrgate.contracts.negotiation
import hugrgate.contracts.nested
import hugrgate.contracts.hierarchy
import hugrgate.contracts.composite
import hugrgate.contracts.conditional
import hugrgate.contracts.crossfield
import hugrgate.contracts.ordinal
import hugrgate.contracts.uncertainty
import hugrgate.contracts.distributions
import hugrgate.contracts.multilabel
import hugrgate.contracts.cost
import hugrgate.contracts.utility
import hugrgate.contracts.risk
import hugrgate.contracts.deadlines
import hugrgate.contracts.context
import hugrgate.contracts.features
import hugrgate.contracts.explanations
import hugrgate.contracts.inheritance
import hugrgate.contracts.composition
import hugrgate.contracts.templates
import hugrgate.contracts.migration
import hugrgate.contracts.lint
import hugrgate.contracts.fuzz

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
    "schema",
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
    "context",
    "features",
    "explanations",
    "inheritance",
    "composition",
    "templates",
    "migration",
    "lint",
    "fuzz",
]
