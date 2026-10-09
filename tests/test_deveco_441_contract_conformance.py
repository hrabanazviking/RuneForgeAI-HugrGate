"""Slice 441 — contract conformance kit."""

from __future__ import annotations

import json

import pytest

from hugrgate.contracts.conformance import (
    assert_conformance,
    run_contract_conformance,
    run_template_conformance,
)
from hugrgate.contracts.templates import (
    ContractTemplate,
    TemplateParameter,
)
from hugrgate.errors import ConformanceError


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


def _broken_template() -> ContractTemplate:
    # 'levels' is declared with a single allowed value that violates
    # the ordinal contract's >=2-levels rule: the declared parameter
    # space itself produces invalid contracts, so the template is
    # non-conformant.
    return ContractTemplate(
        template_id="broken-v1",
        parameters={"levels": TemplateParameter(
            "array", required=True, allowed=(["only"],))},
        body={"schema_version": "2.0", "kind": "ordinal",
              "contract_id": "o", "name": "o",
              "levels": "${levels}"},
    )


def test_conformant_template_passes():
    report = run_template_conformance(_fraud_template())
    assert report.passed, [c for c in report.failures]
    assert len(report.checks) >= 8


def test_broken_template_fails_with_named_checks():
    report = run_template_conformance(_broken_template())
    assert not report.passed
    # _defaults() probes allowed[0] first, so the invalid allowed
    # value surfaces at the defaults check.
    assert "instantiate-defaults" in [c.name for c in report.failures]


def test_assert_conformance_raises_taxonomy_error():
    with pytest.raises(ConformanceError) as exc:
        assert_conformance(run_template_conformance(_broken_template()))
    assert exc.value.code == "conformance_error"
    assert exc.value.recoverable is False
    assert "broken-v1" in exc.value.message


def test_assert_conformance_passes_silently():
    assert_conformance(run_template_conformance(_fraud_template()))


def test_contract_instance_battery():
    contract = _fraud_template().instantiate(miss_cost=100.0,
                                             alarm_cost=10.0,
                                             channel="web")
    report = run_contract_conformance(contract)
    assert report.passed, [c for c in report.failures]


def test_report_is_json_serializable():
    report = run_template_conformance(_fraud_template())
    json.dumps(report.to_dict())
    assert report.to_dict()["template_id"] == "fraud-v1"


def test_cli_check_contract_template(tmp_path, capsys):
    from hugrgate.cli import main
    f = tmp_path / "tpl.json"
    f.write_text(json.dumps(_fraud_template().to_dict()),
                 encoding="utf-8")
    assert main(["check-contract", str(f)]) == 0
    assert "is conformant" in capsys.readouterr().out


def test_cli_check_contract_instance(tmp_path, capsys):
    from hugrgate.cli import main
    contract = _fraud_template().instantiate(miss_cost=100.0,
                                             alarm_cost=10.0,
                                             channel="web")
    f = tmp_path / "c.json"
    f.write_text(json.dumps(contract.to_dict()), encoding="utf-8")
    assert main(["check-contract", "--instance", str(f)]) == 0
    assert "is conformant" in capsys.readouterr().out


def test_cli_check_contract_failing_template(tmp_path, capsys):
    from hugrgate.cli import main
    f = tmp_path / "bad.json"
    f.write_text(json.dumps(_broken_template().to_dict()),
                 encoding="utf-8")
    assert main(["check-contract", str(f)]) == 1
    assert "conformance" in capsys.readouterr().err


def test_cli_check_contract_unreadable(capsys):
    from hugrgate.cli import main
    assert main(["check-contract", "/no/such/file.json"]) == 2
