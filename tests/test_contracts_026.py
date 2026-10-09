"""Gjallarbrú slice 026 — contract schema v2.

Success, failure, and boundary behavior for the DecisionContract base,
the kind registry, canonical hashing, and version gating.
"""

from __future__ import annotations

import json

import pytest

from hugrgate.contracts import (
    CONTRACT_KINDS,
    SCHEMA_VERSION,
    DecisionContract,
    contract_from_dict,
    is_supported_version,
    register_kind,
)
from hugrgate.errors import ContractError, SpecError


def _base_dict(**over):
    d = {
        "schema_version": "2.0",
        "kind": "contract",
        "contract_id": "c-001",
        "name": "smoke",
    }
    d.update(over)
    return d


# --- success ---------------------------------------------------------------

def test_round_trip_preserves_everything():
    c = DecisionContract(contract_id="c-001", name="smoke",
                         description="d", metadata={"a": 1})
    d = c.to_dict()
    assert d["schema_version"] == "2.0"
    assert d["kind"] == "contract"
    back = contract_from_dict(d)
    assert back.to_dict() == d
    assert back.name == "smoke"
    assert back.metadata == {"a": 1}


def test_canonical_hash_is_stable_and_hex():
    c = DecisionContract(contract_id="c-001", metadata={"b": 2, "a": 1})
    h1 = c.canonical_hash()
    h2 = DecisionContract.from_dict(c.to_dict()).canonical_hash()
    assert h1 == h2
    assert len(h1) == 64 and all(ch in "0123456789abcdef" for ch in h1)


def test_hash_changes_with_content():
    a = DecisionContract(contract_id="c-001")
    b = DecisionContract(contract_id="c-002")
    assert a.canonical_hash() != b.canonical_hash()


def test_is_supported_version():
    assert is_supported_version("2.0")
    assert is_supported_version(SCHEMA_VERSION)
    assert not is_supported_version("1.0")
    assert not is_supported_version("")
    assert not is_supported_version(None)
    assert not is_supported_version(2.0)


def test_contract_error_is_a_spec_error():
    assert issubclass(ContractError, SpecError)
    assert ContractError("x").code == "contract_error"


def test_base_validate_accepts_json_values():
    c = DecisionContract(contract_id="c-1")
    c.validate_value({"a": [1, 2, 3]})
    assert c.check_value(None) == []


def test_describe_mentions_kind_and_version():
    c = DecisionContract(contract_id="c-9", name="n")
    s = c.describe()
    assert "contract" in s and "2.0" in s


# --- failure ---------------------------------------------------------------

def test_empty_contract_id_rejected():
    with pytest.raises(ContractError):
        DecisionContract(contract_id="")


def test_unknown_kind_rejected():
    with pytest.raises(ContractError) as ei:
        contract_from_dict(_base_dict(kind="nope"))
    assert ei.value.details["code"] == "unknown_contract_kind"


def test_unsupported_version_rejected_with_migration_hint():
    with pytest.raises(ContractError) as ei:
        contract_from_dict(_base_dict(schema_version="1.0"))
    assert ei.value.details["code"] == "unsupported_schema_version"
    assert "migrat" in ei.value.message.lower()


def test_missing_contract_id_rejected():
    d = _base_dict()
    del d["contract_id"]
    with pytest.raises(ContractError):
        contract_from_dict(d)


def test_non_mapping_input_rejected():
    with pytest.raises(ContractError):
        contract_from_dict(["not", "a", "mapping"])


def test_duplicate_kind_registration_rejected():
    @register_kind
    class _Tmp(DecisionContract):
        kind = "tmp-kind-xyz"

    assert CONTRACT_KINDS["tmp-kind-xyz"] is _Tmp
    with pytest.raises(ContractError):
        @register_kind
        class _Tmp2(DecisionContract):
            kind = "tmp-kind-xyz"
    del CONTRACT_KINDS["tmp-kind-xyz"]


def test_empty_kind_registration_rejected():
    with pytest.raises(ContractError):
        @register_kind
        class _Bad(DecisionContract):
            kind = ""


# --- boundary ----------------------------------------------------------------

def test_non_serializable_metadata_rejected():
    with pytest.raises(ContractError):
        DecisionContract(contract_id="c-1", metadata={"f": object()})


def test_non_serializable_value_rejected():
    c = DecisionContract(contract_id="c-1")
    with pytest.raises(ContractError):
        c.validate_value(object())
    assert len(c.check_value(object())) == 1


def test_metadata_must_be_dict():
    with pytest.raises(ContractError):
        DecisionContract(contract_id="c-1", metadata=["x"])  # type: ignore[arg-type]


def test_to_dict_omits_empty_optionals():
    d = DecisionContract(contract_id="c-1").to_dict()
    assert "name" not in d and "description" not in d and "metadata" not in d
    assert set(d) == {"schema_version", "kind", "contract_id"}
    json.dumps(d)  # always JSON-safe


def test_kind_registry_contains_base():
    assert CONTRACT_KINDS["contract"] is DecisionContract
