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

import hugrgate.contracts.composite as composite
import hugrgate.contracts.composition as composition
import hugrgate.contracts.conditional as conditional
import hugrgate.contracts.context as context
import hugrgate.contracts.cost as cost
import hugrgate.contracts.crossfield as crossfield
import hugrgate.contracts.deadlines as deadlines
import hugrgate.contracts.distributions as distributions
import hugrgate.contracts.explanations as explanations
import hugrgate.contracts.features as features
import hugrgate.contracts.fuzz as fuzz
import hugrgate.contracts.hierarchy as hierarchy
import hugrgate.contracts.inheritance as inheritance
import hugrgate.contracts.lint as lint
import hugrgate.contracts.migration as migration
import hugrgate.contracts.multilabel as multilabel
import hugrgate.contracts.negotiation as negotiation
import hugrgate.contracts.nested as nested
import hugrgate.contracts.ordinal as ordinal
import hugrgate.contracts.risk as risk
import hugrgate.contracts.schema as schema
import hugrgate.contracts.templates as templates
import hugrgate.contracts.uncertainty as uncertainty
import hugrgate.contracts.utility as utility
from hugrgate.contracts.schema import (
    CONTRACT_KINDS,
    SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    DecisionContract,
    contract_from_dict,
    is_supported_version,
    register_kind,
)

__all__ = [
    "CONTRACT_KINDS",
    "SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "DecisionContract",
    "composite",
    "composition",
    "conditional",
    "context",
    "contract_from_dict",
    "cost",
    "crossfield",
    "deadlines",
    "distributions",
    "explanations",
    "features",
    "fuzz",
    "hierarchy",
    "inheritance",
    "is_supported_version",
    "lint",
    "migration",
    "multilabel",
    "negotiation",
    "nested",
    "ordinal",
    "register_kind",
    "risk",
    "schema",
    "templates",
    "uncertainty",
    "utility",
]
