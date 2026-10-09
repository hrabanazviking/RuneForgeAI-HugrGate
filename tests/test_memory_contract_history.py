"""Slice 313 — Contract history features + contract_id propagation."""

from __future__ import annotations

import pytest

from hugrgate.memory import (
    ContractHistory,
    DecisionHistory,
    MemoryQuery,
    Outcome,
    contract_histories,
    contract_key_for,
)
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy_provenance import privacy_preserving_record
from hugrgate.provenance import DecisionRecord
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8)
    base.update(kw)
    return DecisionRecord(**base)


def _record_with_contract(contract_id: str | None,
                          **kw) -> DecisionRecord:
    spec = DecisionSpec(type="binary", statement="approve?")
    result = DecisionResult(value=True, probability=0.9, backend="local",
                            model="m1", metadata=(
                                {"contract_id": contract_id}
                                if contract_id else {}))
    record = privacy_preserving_record({"q": 1}, spec, result,
                                       DecisionPolicy())
    for key, value in kw.items():
        setattr(record, key, value)
    return record


def test_contract_id_propagates_through_privacy_modes():
    for privacy_class in ("public", "standard", "sensitive", "strict",
                          "forbidden"):
        spec = DecisionSpec(type="binary", statement="approve?")
        result = DecisionResult(value=True, probability=0.9,
                                metadata={"contract_id": "deal-7"})
        record = privacy_preserving_record(
            {"q": 1}, spec, result,
            DecisionPolicy(privacy_class=privacy_class))
        assert record.metadata.get("contract_id") == "deal-7", \
            privacy_class


def test_contract_id_absent_when_not_set():
    record = _record_with_contract(None)
    assert "contract_id" not in record.metadata


def test_contract_key_for():
    hist = DecisionHistory()
    with_contract = hist.record(_record_with_contract("deal-7"))
    assert contract_key_for(
        hist.get(with_contract.episode_id)) == "contract:deal-7"
    plain = hist.record(_record())
    key = contract_key_for(hist.get(plain.episode_id))
    assert key.startswith("spec:binary")


def test_contract_histories_grouping():
    hist = DecisionHistory()
    for kind in ("success", "success", "failure"):
        episode = hist.record(_record_with_contract("deal-7"))
        hist.attach_outcome(episode.episode_id, Outcome(kind=kind))
    hist.record(_record_with_contract("deal-9"))
    hist.record(_record())  # synthetic group
    table = contract_histories(hist)
    assert set(table) == {"contract:deal-7", "contract:deal-9",
                          "spec:binary"}
    deal7 = table["contract:deal-7"]
    assert isinstance(deal7, ContractHistory)
    assert deal7.contract_id == "deal-7"
    assert not deal7.synthetic
    assert deal7.decision_count == 3
    assert deal7.accepted_rate == 1.0
    assert deal7.outcome_counts == {"success": 2, "failure": 1}
    assert deal7.success_rate == pytest.approx(2 / 3)
    assert deal7.backends == ("local",)
    deal9 = table["contract:deal-9"]
    assert deal9.success_rate is None  # unlabeled -> None, not 0
    synthetic = table["spec:binary"]
    assert synthetic.synthetic
    assert synthetic.contract_id is None


def test_spec_signature_distinguishes_shapes():
    hist = DecisionHistory()
    hist.record(_record(spec={"type": "binary"}))
    hist.record(_record(spec={"type": "categorical",
                              "options": ["a", "b"]}))
    hist.record(_record(spec={"type": "categorical",
                              "options": ["a", "b"]}))
    table = contract_histories(hist)
    assert len(table) == 2
    cat = table["spec:categorical:options=a|b"]
    assert cat.decision_count == 2
    assert cat.synthetic


def test_query_prefilter_and_limit():
    hist = DecisionHistory()
    for _ in range(6):
        hist.record(_record_with_contract("deal-7"))
    table = contract_histories(hist, limit=4)
    assert table["contract:deal-7"].decision_count == 4
    filtered = contract_histories(hist, query=MemoryQuery(backends={"nope"}))
    assert filtered == {}
    with pytest.raises(ValueError):
        contract_histories(hist, limit=0)


def test_empty_history():
    assert contract_histories(DecisionHistory()) == {}


def test_to_dict():
    hist = DecisionHistory()
    hist.record(_record_with_contract("deal-7"))
    d = contract_histories(hist)["contract:deal-7"].to_dict()
    assert d["contract_id"] == "deal-7"
    assert d["decision_count"] == 1
    assert d["synthetic"] is False
