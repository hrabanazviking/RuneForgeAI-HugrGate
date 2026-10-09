"""Gjallarbrú slice 043 — output explanation contracts."""

from __future__ import annotations

import pytest

from hugrgate.contracts.explanations import (
    EXPLANATION_METADATA_KEY,
    ExplanationContract,
)
from hugrgate.contracts.schema import contract_from_dict
from hugrgate.errors import ContractError
from hugrgate.result import DecisionResult


def _c() -> ExplanationContract:
    return ExplanationContract(
        contract_id="exp-1",
        required_fields=["text", "reasons"],
        min_length=20,
        min_reasons=2,
        must_mention_value=True,
        forbidden_phrases=["trust me"],
    )


def _good_explanation():
    return {
        "text": "We chose approve because income exceeds 50k and no "
                "delinquencies were found.",
        "reasons": ["income 62k > 50k threshold", "zero delinquencies"],
    }


def _result(value="approve", explanation=None):
    return DecisionResult(
        value=value, probability=0.9,
        metadata={EXPLANATION_METADATA_KEY: explanation
                  if explanation is not None else _good_explanation()})


# --- success ---------------------------------------------------------------

def test_good_explanation_passes():
    c = _c()
    assert c.violations("approve", _good_explanation()) == []
    c.validate_explanation("approve", _good_explanation())


def test_check_result_reads_metadata():
    c = _c()
    assert c.check_result(_result()) == []
    c.validate_result(_result())


def test_case_insensitive_mention():
    c = ExplanationContract(contract_id="x", must_mention_value=True)
    c.validate_explanation("APPROVE", {"text": "we chose approve today"})


def test_multilabel_value_needs_all_mentioned():
    c = ExplanationContract(contract_id="x", must_mention_value=True)
    c.validate_explanation(["a", "b"], {"text": "labels a and b apply"})
    problems = c.violations(["a", "b"], {"text": "only label a applies"})
    assert len(problems) == 1


def test_lenient_contract():
    c = ExplanationContract(contract_id="x", must_mention_value=False)
    c.validate_explanation("zzz", {"anything": 1})


def test_round_trip():
    back = contract_from_dict(_c().to_dict())
    assert isinstance(back, ExplanationContract)
    assert back.to_dict() == _c().to_dict()


def test_describe():
    assert "must mention value" in _c().describe()


# --- failure ---------------------------------------------------------------

def test_missing_required_field():
    e = _good_explanation()
    del e["reasons"]
    problems = _c().violations("approve", e)
    assert any("missing field" in p for p in problems)


def test_text_too_short():
    problems = _c().violations("approve", {"text": "approve!", "reasons":
                                           ["r1", "r2"]})
    assert any("min_length" in p for p in problems)


def test_too_few_reasons():
    e = _good_explanation()
    e["reasons"] = ["only one"]
    problems = _c().violations("approve", e)
    assert any("reasons" in p for p in problems)


def test_value_not_mentioned():
    problems = _c().violations(
        "deny", _good_explanation())
    assert any("does not mention" in p for p in problems)


def test_forbidden_phrase():
    e = _good_explanation()
    e["text"] += " Trust me on this."
    problems = _c().violations("approve", e)
    assert any("forbidden phrase" in p for p in problems)


def test_non_mapping_explanation():
    with pytest.raises(ContractError):
        _c().validate_explanation("approve", "looks good")


def test_missing_explanation_in_result():
    c = _c()
    r = DecisionResult(value="approve", probability=0.9, metadata={})
    assert len(c.check_result(r)) > 0
    with pytest.raises(ContractError):
        c.validate_result(r)


def test_violations_aggregated():
    problems = _c().violations("deny", {"text": "x"})
    assert len(problems) >= 3  # missing reasons, short, no mention


def test_bad_result_type():
    with pytest.raises(ContractError):
        _c().check_result("nope")  # type: ignore[arg-type]


# --- construction guards -----------------------------------------------------

def test_bad_min_length():
    with pytest.raises(ContractError):
        ExplanationContract(contract_id="x", min_length=-1)


def test_bad_text_field():
    with pytest.raises(ContractError):
        ExplanationContract(contract_id="x", text_field="")


def test_bad_required_fields():
    with pytest.raises(ContractError):
        ExplanationContract(contract_id="x",
                            required_fields="text")  # type: ignore[arg-type]


def test_bad_must_mention():
    with pytest.raises(ContractError):
        ExplanationContract(contract_id="x",
                            must_mention_value="yes")  # type: ignore[arg-type]


# --- boundary ----------------------------------------------------------------

def test_empty_reasons_ok_when_not_required():
    c = ExplanationContract(contract_id="x", must_mention_value=False)
    c.validate_explanation("v", {"text": "some text here"})


def test_numeric_value_mention():
    c = ExplanationContract(contract_id="x", must_mention_value=True)
    c.validate_explanation(42, {"text": "the answer 42 is final"})
