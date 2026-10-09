"""Decision contract schema v2. Gjallarbrú slice 026.

The v1 decision contract is :class:`hugrgate.spec.DecisionSpec`: an
unversioned dataclass with five fixed types, no identity, and no
canonical form. Schema v2 introduces :class:`DecisionContract`:

- every contract carries a ``schema_version`` (``"2.0"``) and a unique
  ``contract_id``;
- the ``kind`` string is drawn from an explicit registry
  (:data:`CONTRACT_KINDS`), so new decision shapes are discoverable and
  deserializable without touching this module;
- serialization is canonical JSON with a sha256 content hash
  (:meth:`DecisionContract.canonical_hash`), giving contracts a stable
  identity for caching, provenance, and negotiation;
- :meth:`DecisionContract.validate_value` is the validation hook every
  later Campaign II slice extends.

``DecisionSpec`` is untouched: v2 contracts live alongside it and
migration between the two is slice 047's job.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from hugrgate.errors import ContractError

__all__ = [
    "CONTRACT_KINDS",
    "SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "DecisionContract",
    "contract_from_dict",
    "is_supported_version",
    "register_kind",
]

#: Current contract schema version.
SCHEMA_VERSION = "2.0"

#: Schema versions this codebase can read.
SUPPORTED_SCHEMA_VERSIONS = ("2.0",)

#: kind string -> DecisionContract subclass. Populated by @register_kind.
CONTRACT_KINDS: dict[str, type[DecisionContract]] = {}


def is_supported_version(version: object) -> bool:
    """True when ``version`` is a schema version this code can read."""
    return isinstance(version, str) and version in SUPPORTED_SCHEMA_VERSIONS


def register_kind(cls: type[DecisionContract]) -> type[DecisionContract]:
    """Class decorator registering a contract ``kind`` for deserialization.

    The class must define a non-empty ``kind`` ClassVar unique in the
    registry; re-registration of the same kind raises ContractError.
    """
    kind = getattr(cls, "kind", "")
    if not isinstance(kind, str) or not kind:
        raise ContractError(
            f"cannot register {cls.__name__}: empty contract kind",
            code="empty_contract_kind",
        )
    if kind in CONTRACT_KINDS and CONTRACT_KINDS[kind] is not cls:
        raise ContractError(
            f"contract kind {kind!r} already registered by "
            f"{CONTRACT_KINDS[kind].__name__}",
            code="duplicate_contract_kind",
        )
    CONTRACT_KINDS[kind] = cls
    return cls


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str)


@dataclass
class DecisionContract:
    """Base class for all v2 decision contracts.

    Concrete contracts subclass this, set the ``kind`` ClassVar, and add
    their own dataclass fields plus ``_payload_dict`` / ``_from_payload``
    / ``validate_value`` implementations.
    """

    kind: ClassVar[str] = "contract"

    contract_id: str
    name: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.contract_id, str) or not self.contract_id:
            raise ContractError("contract_id must be a non-empty string",
                                code="bad_contract_id")
        if not isinstance(self.name, str):
            raise ContractError("contract name must be a string",
                                code="bad_contract_name")
        if not isinstance(self.description, str):
            raise ContractError("contract description must be a string",
                                code="bad_contract_description")
        if not isinstance(self.metadata, dict):
            raise ContractError("contract metadata must be a dict",
                                code="bad_contract_metadata")
        try:
            json.dumps(self.metadata)
        except (TypeError, ValueError) as e:
            raise ContractError(
                f"contract metadata must be JSON-serializable: {e}",
                code="metadata_not_serializable") from e

    @property
    def schema_version(self) -> str:
        """The schema version this contract was written against."""
        return SCHEMA_VERSION

    # -- serialization ----------------------------------------------------

    def _payload_dict(self) -> dict[str, Any]:
        """Kind-specific payload. Base contracts carry no payload."""
        return {}

    def to_dict(self) -> dict[str, Any]:
        """Full versioned serialization of this contract."""
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "contract_id": self.contract_id,
        }
        if self.name:
            d["name"] = self.name
        if self.description:
            d["description"] = self.description
        d.update(self._payload_dict())
        if self.metadata:
            d["metadata"] = dict(self.metadata)
        return d

    @classmethod
    def _from_payload(cls, d: Mapping[str, Any],
                      common: dict[str, Any]) -> DecisionContract:
        """Build from a kind payload dict plus common fields."""
        return cls(**common)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> DecisionContract:
        """Deserialize any registered contract kind from a dict.

        Raises ContractError on unknown kinds or unsupported schema
        versions — never silently misreads a contract.
        """
        if not isinstance(d, Mapping):
            raise ContractError("contract must deserialize from a mapping",
                                code="contract_not_mapping")
        version = d.get("schema_version", "1.0")
        if not is_supported_version(version):
            raise ContractError(
                f"unsupported contract schema version: {version!r}; "
                f"supported: {list(SUPPORTED_SCHEMA_VERSIONS)} "
                f"(migrate v1 DecisionSpec contracts via "
                f"hugrgate.contracts.migration)",
                code="unsupported_schema_version",
                version=version)
        kind = d.get("kind")
        if kind not in CONTRACT_KINDS:
            raise ContractError(
                f"unknown contract kind: {kind!r}; "
                f"known kinds: {sorted(CONTRACT_KINDS)}",
                code="unknown_contract_kind", kind=kind)
        sub = CONTRACT_KINDS[kind]
        if not isinstance(d.get("contract_id"), str) or not d.get("contract_id"):
            raise ContractError("contract dict needs a contract_id string",
                                code="missing_contract_id")
        metadata = d.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ContractError("contract metadata must be a dict",
                                code="bad_contract_metadata")
        common = {
            "contract_id": d["contract_id"],
            "name": d.get("name", ""),
            "description": d.get("description", ""),
            "metadata": dict(metadata),
        }
        try:
            return sub._from_payload(d, common)
        except (TypeError, ValueError, KeyError) as e:
            raise ContractError(
                f"malformed {kind!r} contract payload: {e}",
                code="malformed_contract_payload", kind=kind) from e

    def canonical_hash(self) -> str:
        """sha256 of the canonical JSON form — the contract's stable id."""
        return hashlib.sha256(
            _canonical_json(self.to_dict()).encode("utf-8")).hexdigest()

    # -- validation --------------------------------------------------------

    def validate_value(self, value: Any) -> None:
        """Raise ContractError if ``value`` violates this contract.

        Base implementation accepts anything JSON-serializable; concrete
        kinds narrow the decision space.
        """
        try:
            json.dumps(value)
        except (TypeError, ValueError) as e:
            raise ContractError(
                f"contract value is not JSON-serializable: {e}",
                code="value_not_serializable") from e

    def check_value(self, value: Any) -> list[str]:
        """Non-raising validation: return a list of violation messages."""
        try:
            self.validate_value(value)
            return []
        except ContractError as e:
            return [e.message]

    # -- introspection ------------------------------------------------------

    def describe(self) -> str:
        """One-line human summary of the contract."""
        label = self.name or self.contract_id
        return (f"{self.kind} contract {label!r} "
                f"(schema {self.schema_version})")


def contract_from_dict(d: Mapping[str, Any]) -> DecisionContract:
    """Deserialize any registered v2 contract from a plain dict."""
    return DecisionContract.from_dict(d)


# The base kind is registered so bare DecisionContract round-trips.
register_kind(DecisionContract)
