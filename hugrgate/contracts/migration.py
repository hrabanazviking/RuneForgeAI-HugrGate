"""Contract migration engine — v1 DecisionSpec ↔ v2 contracts.

Gjallarbrú slice 047.

``DecisionSpec`` (v1) and ``DecisionContract`` (v2) have lived side by
side since slice 026, and ``from_dict``'s version error has pointed at
this module since then. The migration engine bridges them:

- :func:`spec_to_contract`: v1 → v2. categorical → flat
  nested-categorical; binary → nested-categorical ``["true", "false"]``
  (statement preserved in ``description``); ordinal → ordinal (default
  anchors); numeric → numeric-interval; multilabel → multilabel-cardinality
  (no rules). Metadata carries over.
- :func:`contract_to_spec`: v2 → v1 for the four unambiguous kinds
  (flat nested → categorical, ordinal, numeric-interval, rule-free
  multilabel); anything else raises — no silent lossy downgrades.
- :class:`MigrationReport`: the result plus ``warnings`` and a ``lossy``
  flag, so callers know exactly what changed.
- :data:`MIGRATIONS`: the ``(from_version, to_version) → function``
  registry; :func:`migrate` dispatches a raw dict on its
  ``schema_version`` (absent = ``"1.0"``).

Migrations are total on their documented domain and loud everywhere else.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.contracts.multilabel import MultilabelContract
from hugrgate.contracts.nested import NestedCategoricalContract
from hugrgate.contracts.ordinal import OrdinalContract
from hugrgate.contracts.schema import (
    SUPPORTED_SCHEMA_VERSIONS,
    DecisionContract,
    contract_from_dict,
)
from hugrgate.contracts.uncertainty import NumericIntervalContract
from hugrgate.errors import ContractError, SpecError
from hugrgate.spec import DecisionSpec

__all__ = [
    "MIGRATIONS",
    "MigrationReport",
    "contract_to_spec",
    "migrate",
    "migrate_spec_dict",
    "register_migration",
    "spec_to_contract",
]

#: (from_version, to_version) -> migration function over raw dicts.
MIGRATIONS: dict[tuple[str, str], Callable[[Mapping[str, Any]],
                                           Mapping[str, Any]]] = {}


def register_migration(from_version: str, to_version: str,
                       func: Callable[[Mapping[str, Any]],
                                      Mapping[str, Any]]) -> None:
    """Register a dict-level migration between schema versions."""
    if not from_version or not to_version:
        raise ContractError("migration versions must be non-empty strings",
                            code="bad_migration")
    if not callable(func):
        raise ContractError("migration must be callable",
                            code="bad_migration")
    key = (from_version, to_version)
    if key in MIGRATIONS:
        raise ContractError(f"migration {from_version} -> {to_version} "
                            f"already registered", code="duplicate_migration")
    MIGRATIONS[key] = func


@dataclass
class MigrationReport:
    """What a migration did, and what it could not preserve."""

    source_version: str
    target_version: str
    result: DecisionContract
    warnings: list[str] = field(default_factory=list)
    lossy: bool = False

    def describe(self) -> str:
        flag = "LOSSY" if self.lossy else "exact"
        lines = [f"migration {self.source_version} -> {self.target_version} "
                 f"({flag}): {self.result.describe()}"]
        lines.extend(f"  warning: {w}" for w in self.warnings)
        return "\n".join(lines)


def spec_to_contract(spec: DecisionSpec, contract_id: str, *,
                     name: str = "", description: str = "",
                     ) -> tuple[DecisionContract, MigrationReport]:
    """Migrate a v1 DecisionSpec to the equivalent v2 contract."""
    if not isinstance(spec, DecisionSpec):
        raise ContractError(f"spec_to_contract needs a DecisionSpec, got "
                            f"{type(spec).__name__}",
                            code="bad_migration_source")
    warnings: list[str] = []
    lossy = False
    metadata = dict(spec.metadata)

    if spec.type == "categorical":
        assert spec.options is not None
        result: DecisionContract = NestedCategoricalContract(
            contract_id=contract_id, name=name, description=description,
            metadata=metadata, options=list(spec.options))
    elif spec.type == "binary":
        result = NestedCategoricalContract(
            contract_id=contract_id, name=name,
            description=description or spec.statement or "",
            metadata=metadata, options=["true", "false"])
        if spec.statement:
            warnings.append("binary statement preserved in description")
    elif spec.type == "ordinal":
        assert spec.levels is not None
        result = OrdinalContract(
            contract_id=contract_id, name=name, description=description,
            metadata=metadata, levels=list(spec.levels))
    elif spec.type == "numeric":
        assert spec.minimum is not None and spec.maximum is not None
        result = NumericIntervalContract(
            contract_id=contract_id, name=name, description=description,
            metadata=metadata, minimum=spec.minimum,
            maximum=spec.maximum)
    elif spec.type == "multilabel":
        assert spec.labels is not None
        result = MultilabelContract(
            contract_id=contract_id, name=name, description=description,
            metadata=metadata, labels=list(spec.labels))
    else:  # pragma: no cover - DecisionSpec guards its own types
        raise ContractError(f"unknown spec type: {spec.type!r}",
                            code="bad_migration_source")

    report = MigrationReport(source_version="1.0", target_version="2.0",
                             result=result, warnings=warnings, lossy=lossy)
    return result, report


def contract_to_spec(contract: DecisionContract) -> DecisionSpec:
    """Migrate a v2 contract back to v1 where the mapping is unambiguous.

    Supported: flat nested-categorical → categorical (or binary when the
    options are exactly ``["true", "false"]`` and a statement survives in
    the description), ordinal, numeric-interval, rule-free
    multilabel-cardinality. Everything else raises ContractError.
    """
    if not isinstance(contract, DecisionContract):
        raise ContractError(f"contract_to_spec needs a DecisionContract, "
                            f"got {type(contract).__name__}",
                            code="bad_migration_source")
    metadata = dict(contract.metadata)
    metadata.pop("derived_from", None)

    if isinstance(contract, NestedCategoricalContract) and not contract.children:
        assert contract.options is not None
        if (contract.options == ["true", "false"]
                and contract.description):
            return DecisionSpec(type="binary",
                                statement=contract.description,
                                metadata=metadata)
        return DecisionSpec(type="categorical",
                            options=list(contract.options),
                            metadata=metadata)
    if isinstance(contract, OrdinalContract):
        return DecisionSpec(type="ordinal", levels=list(contract.levels),
                            metadata=metadata)
    if isinstance(contract, NumericIntervalContract):
        if contract.max_width is not None or contract.min_confidence is not None:
            raise ContractError(
                "numeric-interval with width/confidence guards has no v1 "
                "equivalent", code="lossy_downgrade")
        return DecisionSpec(type="numeric", minimum=contract.minimum,
                            maximum=contract.maximum, metadata=metadata)
    if isinstance(contract, MultilabelContract):
        d = contract.to_dict()
        rules = [k for k in ("min_count", "max_count", "exact_count",
                             "required", "forbidden", "implies", "excludes")
                 if k in d]
        if rules:
            raise ContractError(
                f"multilabel-cardinality with rules {rules} has no v1 "
                f"equivalent", code="lossy_downgrade")
        return DecisionSpec(type="multilabel", labels=list(contract.labels),
                            metadata=metadata)
    raise ContractError(
        f"kind {contract.kind!r} has no v1 DecisionSpec equivalent",
        code="no_downgrade_path")


def migrate_spec_dict(d: Mapping[str, Any], contract_id: str, *,
                      name: str = "", description: str = "",
                      ) -> tuple[DecisionContract, MigrationReport]:
    """Migrate a raw v1 spec dict to a v2 contract."""
    try:
        spec = DecisionSpec.from_dict(dict(d))
    except SpecError as e:
        raise ContractError(f"cannot migrate: not a valid v1 spec: {e}",
                            code="bad_migration_source") from e
    return spec_to_contract(spec, contract_id, name=name,
                            description=description)


def _migrate_v1_dict_to_v2(d: Mapping[str, Any]) -> Mapping[str, Any]:
    """Dict-level 1.0 -> 2.0 migration used by :func:`migrate`."""
    contract, _ = migrate_spec_dict(
        d, contract_id=d.get("contract_id", "migrated"))
    return contract.to_dict()


register_migration("1.0", "2.0", _migrate_v1_dict_to_v2)


def migrate(d: Mapping[str, Any], to_version: str = "2.0") -> DecisionContract:
    """Migrate a raw contract dict to ``to_version`` via the registry.

    Dicts without ``schema_version`` are treated as v1 (``"1.0"``). Dicts
    already at ``to_version`` deserialize directly. Unknown paths raise.
    """
    if not isinstance(d, Mapping):
        raise ContractError("migrate needs a mapping",
                            code="bad_migration_source")
    from_version = d.get("schema_version", "1.0")
    if from_version == to_version:
        if to_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ContractError(
                f"target version {to_version!r} is not readable here",
                code="unsupported_schema_version")
        return contract_from_dict(d)
    key = (from_version, to_version)
    if key not in MIGRATIONS:
        raise ContractError(
            f"no migration path {from_version} -> {to_version}; known: "
            f"{sorted(f'{a}->{b}' for a, b in MIGRATIONS)}",
            code="no_migration_path")
    return contract_from_dict(MIGRATIONS[key](d))
