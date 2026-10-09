"""Gjallarbrú slice 047 — contract migration engine."""

from __future__ import annotations

import pytest

from hugrgate.contracts.migration import (
    MIGRATIONS,
    MigrationReport,
    contract_to_spec,
    migrate,
    register_migration,
    spec_to_contract,
)
from hugrgate.contracts.multilabel import MultilabelContract
from hugrgate.contracts.nested import NestedCategoricalContract
from hugrgate.contracts.ordinal import OrdinalContract
from hugrgate.contracts.uncertainty import NumericIntervalContract
from hugrgate.errors import ContractError
from hugrgate.spec import DecisionSpec

# --- spec -> contract ----------------------------------------------------------

def test_categorical_migrates():
    spec = DecisionSpec(type="categorical", options=["a", "b"],
                        metadata={"src": "v1"})
    c, report = spec_to_contract(spec, "c-1", name="n")
    assert isinstance(c, NestedCategoricalContract)
    assert c.options == ["a", "b"]
    assert c.metadata["src"] == "v1" and c.name == "n"
    assert not report.lossy and report.warnings == []
    c.validate_value("a")


def test_binary_migrates_with_statement():
    spec = DecisionSpec(type="binary", statement="launch?")
    c, report = spec_to_contract(spec, "c-1")
    assert isinstance(c, NestedCategoricalContract)
    assert c.options == ["true", "false"]
    assert c.description == "launch?"
    assert any("statement" in w for w in report.warnings)


def test_ordinal_migrates():
    spec = DecisionSpec(type="ordinal", levels=["lo", "hi"])
    c, _ = spec_to_contract(spec, "c-1")
    assert isinstance(c, OrdinalContract) and c.levels == ["lo", "hi"]


def test_numeric_migrates():
    spec = DecisionSpec(type="numeric", minimum=0.0, maximum=1.0)
    c, _ = spec_to_contract(spec, "c-1")
    assert isinstance(c, NumericIntervalContract)
    assert (c.minimum, c.maximum) == (0.0, 1.0)


def test_multilabel_migrates():
    spec = DecisionSpec(type="multilabel", labels=["a", "b"])
    c, _ = spec_to_contract(spec, "c-1")
    assert isinstance(c, MultilabelContract) and c.labels == ["a", "b"]


def test_migrated_value_spaces_agree():
    specs = [
        DecisionSpec(type="categorical", options=["a", "b"]),
        DecisionSpec(type="ordinal", levels=["x", "y"]),
        DecisionSpec(type="numeric", minimum=0, maximum=5),
        DecisionSpec(type="multilabel", labels=["m", "n"]),
    ]
    for spec in specs:
        c, _ = spec_to_contract(spec, "c")
        # every v1 value validates under the migrated contract
        if spec.type == "numeric":
            c.validate_value(2.5)
        elif spec.type == "multilabel":
            c.validate_value(["m"])
        elif spec.type == "categorical":
            c.validate_value("a")
        else:
            c.validate_value("x")


# --- contract -> spec ------------------------------------------------------------

def test_round_trip_categorical():
    spec = DecisionSpec(type="categorical", options=["a", "b", "c"])
    c, _ = spec_to_contract(spec, "c")
    back = contract_to_spec(c)
    assert back.type == "categorical" and back.options == ["a", "b", "c"]


def test_round_trip_binary():
    spec = DecisionSpec(type="binary", statement="go?")
    c, _ = spec_to_contract(spec, "c")
    back = contract_to_spec(c)
    assert back.type == "binary" and back.statement == "go?"


def test_round_trip_ordinal_numeric_multilabel():
    for spec in (DecisionSpec(type="ordinal", levels=["a", "b"]),
                 DecisionSpec(type="numeric", minimum=1, maximum=2),
                 DecisionSpec(type="multilabel", labels=["a"])):
        c, _ = spec_to_contract(spec, "c")
        assert contract_to_spec(c).to_dict() == spec.to_dict()


def test_guarded_numeric_has_no_downgrade():
    c = NumericIntervalContract(contract_id="x", minimum=0.0, maximum=1.0,
                                max_width=0.5)
    with pytest.raises(ContractError) as ei:
        contract_to_spec(c)
    assert ei.value.details["code"] == "lossy_downgrade"


def test_ruled_multilabel_has_no_downgrade():
    c = MultilabelContract(contract_id="x", labels=["a", "b"], min_count=1)
    with pytest.raises(ContractError):
        contract_to_spec(c)


def test_exotic_kind_has_no_downgrade():
    from hugrgate.contracts.cost import CostSensitiveContract
    c = CostSensitiveContract(contract_id="x", outcomes=["a"],
                              costs={"a": {"a": 0.0}})
    with pytest.raises(ContractError):
        contract_to_spec(c)


# --- migrate() dispatch ------------------------------------------------------------

def test_migrate_v1_dict():
    c = migrate({"type": "ordinal", "levels": ["a", "b"]})
    assert isinstance(c, OrdinalContract)


def test_migrate_v2_dict_passes_through():
    c, _ = spec_to_contract(DecisionSpec(type="binary", statement="s"),
                            "c")
    assert migrate(c.to_dict()).to_dict() == c.to_dict()


def test_migrate_unknown_path():
    with pytest.raises(ContractError) as ei:
        migrate({"schema_version": "2.0", "kind": "contract",
                 "contract_id": "c"}, to_version="9.9")
    assert ei.value.details["code"] in ("no_migration_path",
                                        "unsupported_schema_version")


def test_migrate_bad_input():
    with pytest.raises(ContractError):
        migrate("nope")  # type: ignore[arg-type]
    with pytest.raises(ContractError):
        migrate({"type": "bogus"})


def test_register_migration_guards():
    with pytest.raises(ContractError):
        register_migration("1.0", "2.0", lambda d: d)  # duplicate
    with pytest.raises(ContractError):
        register_migration("", "2.0", lambda d: d)


def test_registry_has_v1_to_v2():
    assert ("1.0", "2.0") in MIGRATIONS


def test_migration_report_describe():
    _, report = spec_to_contract(
        DecisionSpec(type="binary", statement="s"), "c")
    assert isinstance(report, MigrationReport)
    assert "1.0 -> 2.0" in report.describe()
