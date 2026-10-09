"""Gjallarbrú slice 048 — contract linting."""

from __future__ import annotations

import pytest

from hugrgate.contracts.composite import CompositeContract
from hugrgate.contracts.cost import CostSensitiveContract
from hugrgate.contracts.deadlines import TimedContract
from hugrgate.contracts.distributions import DistributionContract
from hugrgate.contracts.explanations import ExplanationContract
from hugrgate.contracts.features import FeatureContract
from hugrgate.contracts.lint import (
    ERROR,
    INFO,
    LINT_CHECKS,
    WARNING,
    LintFinding,
    LintReport,
    lint_all,
    lint_contract,
    lint_template,
    register_check,
)
from hugrgate.contracts.multilabel import MultilabelContract
from hugrgate.contracts.nested import NestedCategoricalContract
from hugrgate.contracts.ordinal import OrdinalContract
from hugrgate.contracts.schema import DecisionContract
from hugrgate.contracts.templates import ContractTemplate, TemplateParameter
from hugrgate.contracts.uncertainty import NumericIntervalContract
from hugrgate.errors import ContractError
from hugrgate.spec import DecisionSpec


def _base(**kw):
    kw.setdefault("contract_id", "c")
    kw.setdefault("name", "n")
    kw.setdefault("description", "d")
    kw.setdefault("metadata", {"owner": "yrsa"})
    return kw


# --- generic ---------------------------------------------------------------

def test_undocumented_warns():
    c = DecisionContract(contract_id="c")
    codes = [f.code for f in lint_contract(c).warnings]
    assert "undocumented" in codes


def test_no_metadata_info():
    c = DecisionContract(contract_id="c", name="n", description="d")
    codes = [f.code for f in lint_contract(c).infos]
    assert "no_metadata" in codes


def test_single_option_warns():
    c = NestedCategoricalContract(**_base(options=["only"]))
    assert "single_option" in [f.code for f in lint_contract(c).warnings]


# --- kind-specific -----------------------------------------------------------

def test_zero_cost_matrix_errors():
    c = CostSensitiveContract(
        **_base(outcomes=["a", "b"],
                costs={"a": {"a": 0.0, "b": 0.0},
                       "b": {"a": 0.0, "b": 0.0}}))
    rep = lint_contract(c)
    assert rep.has_errors
    assert "zero_cost_matrix" in [f.code for f in rep.errors]


def test_nonzero_correct_cost_warns():
    c = CostSensitiveContract(
        **_base(outcomes=["a", "b"],
                costs={"a": {"a": 1.0, "b": 0.0},
                       "b": {"a": 0.0, "b": 0.0}}))
    assert "nonzero_correct_cost" in [f.code for f in
                                      lint_contract(c).warnings]


def test_vacuous_width_guard_warns():
    c = NumericIntervalContract(**_base(minimum=0.0, maximum=1.0,
                                        max_width=2.0))
    assert "vacuous_width_guard" in [f.code for f in
                                     lint_contract(c).warnings]


def test_tight_width_guard_clean():
    c = NumericIntervalContract(**_base(minimum=0.0, maximum=1.0,
                                        max_width=0.5))
    assert "vacuous_width_guard" not in [f.code for f in
                                         lint_contract(c).findings]


def test_anchors_not_spanning_warn():
    c = OrdinalContract(
        **_base(levels=["a", "b", "c"],
                anchors={"a": 0.4, "b": 0.5, "c": 0.6}))
    codes = [f.code for f in lint_contract(c).warnings]
    assert "anchors_not_grounded" in codes and "anchors_not_capped" in codes


def test_default_anchors_info():
    c = OrdinalContract(**_base(levels=["a", "b"]))
    assert "default_anchors" in [f.code for f in lint_contract(c).infos]


def test_ruled_multilabel_clean_of_info():
    c = MultilabelContract(**_base(labels=["a", "b"], min_count=1))
    assert "no_cardinality_rules" not in [f.code for f in
                                          lint_contract(c).infos]


def test_ruleless_multilabel_info():
    c = MultilabelContract(**_base(labels=["a", "b"]))
    assert "no_cardinality_rules" in [f.code for f in
                                      lint_contract(c).infos]


def test_single_field_composite_warns():
    inner = DecisionSpec(type="categorical", options=["a", "b"])
    c = CompositeContract(**_base(fields={"only": inner}))
    assert "single_branch" in [f.code for f in lint_contract(c).warnings]


def test_all_optional_features_info():
    from hugrgate.contracts.features import FeatureSpec
    c = FeatureContract(
        **_base(features=[FeatureSpec(name="x", required=False).to_dict()]))
    assert "all_features_optional" in [f.code for f in
                                       lint_contract(c).infos]


def test_unconstrained_distribution_warns():
    c = DistributionContract(**_base(outcomes=["a", "b"]))
    assert "no_constraints" in [f.code for f in lint_contract(c).warnings]


def test_lax_explanation_warns():
    c = ExplanationContract(**_base())
    assert "no_required_sections" in [f.code for f in
                                      lint_contract(c).warnings]


def test_past_window_warns():
    inner = DecisionSpec(type="categorical", options=["a", "b"])
    c = TimedContract(**_base(inner=inner, not_before=1000.0,
                               not_after=2000.0))
    assert "window_in_past" in [f.code for f in lint_contract(c).warnings]


def test_future_window_clean():
    import time
    inner = DecisionSpec(type="categorical", options=["a", "b"])
    now = time.time()
    c = TimedContract(**_base(inner=inner, not_before=now + 3600,
                               not_after=now + 7200))
    assert "window_in_past" not in [f.code for f in
                                    lint_contract(c).findings]


# --- template linting ----------------------------------------------------------

def test_template_lint():
    t = ContractTemplate(
        template_id="t",
        parameters={
            "used": TemplateParameter("string", description="used"),
            "unused": TemplateParameter("string", description="unused"),
            "nodesc": TemplateParameter("string"),
        },
        body={"schema_version": "2.0", "kind": "contract",
              "contract_id": "${used}",
              "metadata": {"x": "${nodesc}"}})
    rep = lint_template(t)
    codes = [(f.severity, f.code) for f in rep.findings]
    assert (INFO, "unused_parameter") in codes
    assert (WARNING, "undocumented_parameter") in codes


# --- report API ------------------------------------------------------------------

def test_report_api():
    rep = LintReport(findings=[
        LintFinding(ERROR, "e1", "m"), LintFinding(WARNING, "w1", "m"),
        LintFinding(INFO, "i1", "m")])
    assert rep.has_errors and not rep.clean
    assert len(rep.errors) == 1 and len(rep.warnings) == 1
    assert set(rep.by_severity()) == {ERROR, WARNING, INFO}
    assert "1 error(s)" in rep.describe()
    assert LintReport().clean and "clean" in LintReport().describe()


def test_finding_guards():
    with pytest.raises(ContractError):
        LintFinding("bogus", "c", "m")
    with pytest.raises(ContractError):
        LintFinding(INFO, "", "m")
    with pytest.raises(ContractError):
        register_check("nope")  # type: ignore[arg-type]
    with pytest.raises(ContractError):
        lint_contract("nope")  # type: ignore[arg-type]
    with pytest.raises(ContractError):
        lint_template("nope")  # type: ignore[arg-type]


def test_custom_check_registration():
    def house_rule(c):
        return []
    n = len(LINT_CHECKS)
    register_check(house_rule)
    assert len(LINT_CHECKS) == n + 1
    LINT_CHECKS.pop()


def test_lint_all():
    good = NestedCategoricalContract(**_base(options=["a", "b"]))
    bad = CostSensitiveContract(
        **_base(outcomes=["a"],
                costs={"a": {"a": 0.0}}))
    rep = lint_all([good, bad])
    assert rep.has_errors
    assert {f.contract_id for f in rep.errors} == {"c"}
