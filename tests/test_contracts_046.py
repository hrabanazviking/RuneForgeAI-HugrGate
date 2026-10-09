"""Gjallarbrú slice 046 — contract templates."""

from __future__ import annotations

import pytest

from hugrgate.contracts.ordinal import OrdinalContract
from hugrgate.contracts.schema import contract_from_dict
from hugrgate.contracts.templates import (
    ContractTemplate,
    TemplateLibrary,
    TemplateParameter,
    find_placeholders,
)
from hugrgate.errors import ContractError


def _fraud_template() -> ContractTemplate:
    return ContractTemplate(
        template_id="fraud-v1",
        description="cost-sensitive fraud triage",
        parameters={
            "miss_cost": TemplateParameter("number", required=True),
            "alarm_cost": TemplateParameter("number", required=True),
            "currency": TemplateParameter("string", required=False,
                                          default="USD"),
            "channel": TemplateParameter("string", required=True,
                                         allowed=("web", "pos", "atm")),
        },
        body={
            "schema_version": "2.0",
            "kind": "cost-sensitive",
            "contract_id": "fraud-${channel}",
            "name": "fraud triage [${currency}]",
            "outcomes": ["legit", "fraud"],
            "costs": {
                "legit": {"legit": 0.0, "fraud": "${miss_cost}"},
                "fraud": {"legit": "${alarm_cost}", "fraud": 0.0},
            },
        },
    )


# --- success ---------------------------------------------------------------

def test_instantiate_fills_params():
    c = _fraud_template().instantiate(miss_cost=100.0, alarm_cost=10.0,
                                      channel="web")
    assert c.contract_id == "fraud-web"
    assert c.name == "fraud triage [USD]"  # default applied
    assert c.matrix.cost("legit", "fraud") == 100.0  # raw number, not str
    assert c.matrix.cost("fraud", "legit") == 10.0


def test_textual_interpolation():
    t = ContractTemplate(
        template_id="t",
        parameters={"who": TemplateParameter("string")},
        body={"schema_version": "2.0", "kind": "contract",
              "contract_id": "c-${who}-v2", "name": "hello ${who}"})
    c = t.instantiate(who="yrsa")
    assert c.contract_id == "c-yrsa-v2" and c.name == "hello yrsa"


def test_raw_injection_of_list():
    t = ContractTemplate(
        template_id="t",
        parameters={"levels": TemplateParameter("array")},
        body={"schema_version": "2.0", "kind": "ordinal",
              "contract_id": "o", "levels": "${levels}"})
    c = t.instantiate(levels=["a", "b", "c"])
    assert isinstance(c, OrdinalContract) and c.levels == ["a", "b", "c"]


def test_library():
    lib = TemplateLibrary()
    lib.register(_fraud_template())
    assert "fraud-v1" in lib and len(lib) == 1
    assert lib.template_ids() == ["fraud-v1"]
    c = lib.instantiate("fraud-v1", miss_cost=50.0, alarm_cost=5.0,
                        channel="atm")
    assert c.contract_id == "fraud-atm"
    with pytest.raises(ContractError):
        lib.register(_fraud_template())  # duplicate
    with pytest.raises(ContractError):
        lib.get("nope")


def test_template_round_trip():
    t = _fraud_template()
    back = ContractTemplate.from_dict(t.to_dict())
    assert back.to_dict() == t.to_dict()
    assert back.parameter_names == t.parameter_names


def test_find_placeholders():
    assert find_placeholders({"a": "${x} and ${y}", "b": ["${x}"]}) == \
        ["x", "y", "x"]


def test_allowed_value_ok():
    _fraud_template().instantiate(miss_cost=1.0, alarm_cost=1.0,
                                  channel="pos")


# --- failure ---------------------------------------------------------------

def test_missing_required_param():
    with pytest.raises(ContractError) as ei:
        _fraud_template().instantiate(alarm_cost=1.0, channel="web")
    assert ei.value.details["code"] == "missing_template_parameter"


def test_unknown_param_rejected():
    with pytest.raises(ContractError):
        _fraud_template().instantiate(miss_cost=1.0, alarm_cost=1.0,
                                      channel="web", bogus=1)


def test_wrong_type_rejected():
    with pytest.raises(ContractError):
        _fraud_template().instantiate(miss_cost="lots", alarm_cost=1.0,
                                      channel="web")


def test_disallowed_value_rejected():
    with pytest.raises(ContractError):
        _fraud_template().instantiate(miss_cost=1.0, alarm_cost=1.0,
                                      channel="sms")


def test_undeclared_placeholder_rejected_at_construction():
    with pytest.raises(ContractError) as ei:
        ContractTemplate(
            template_id="bad",
            parameters={},
            body={"schema_version": "2.0", "kind": "contract",
                  "contract_id": "${nope}"})
    assert ei.value.details["code"] == "undeclared_placeholder"


def test_dangling_placeholder_rejected_at_construction():
    with pytest.raises(ContractError) as ei:
        ContractTemplate(
            template_id="bad",
            parameters={"opt": TemplateParameter("string", required=False)},
            body={"schema_version": "2.0", "kind": "contract",
                  "contract_id": "${opt}"})
    assert ei.value.details["code"] == "dangling_placeholder"


def test_instantiated_body_must_be_valid_contract():
    t = ContractTemplate(
        template_id="bad",
        parameters={"x": TemplateParameter("string")},
        body={"schema_version": "2.0", "kind": "nope-kind",
              "contract_id": "${x}"})
    with pytest.raises(ContractError):
        t.instantiate(x="y")


def test_bad_parameter_type():
    with pytest.raises(ContractError):
        TemplateParameter("uuid")


def test_bad_default_type():
    with pytest.raises(ContractError):
        TemplateParameter("number", required=False, default="x")


def test_empty_template_id():
    with pytest.raises(ContractError):
        ContractTemplate(template_id="", body={"a": 1})


# --- boundary ----------------------------------------------------------------

def test_numeric_zero_is_a_valid_param():
    t = ContractTemplate(
        template_id="t",
        parameters={"n": TemplateParameter("number")},
        body={"schema_version": "2.0", "kind": "contract",
              "contract_id": "c", "metadata": {"n": "${n}"}})
    c = t.instantiate(n=0)
    assert c.metadata["n"] == 0


def test_parameter_dict_round_trip():
    p = TemplateParameter("string", required=False, default="d",
                          allowed=("d", "e"), description="desc")
    assert TemplateParameter.from_dict(p.to_dict()).to_dict() == p.to_dict()
