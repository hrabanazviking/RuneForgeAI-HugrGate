"""Slice 119 — Ensemble provenance.

Ensemble rulings land in the ProvenanceStore with their full council
detail: strategy, members, votes, weights, minority report — plus the
slice-015 integrity chain.
"""

from __future__ import annotations

import pytest
from ensemble_fakes import CAT_SPEC, ConstantBackend

from hugrgate.ensemble import (
    Ensemble,
    MembershipManager,
    find_ensemble_records,
    record_ensemble_decision,
)
from hugrgate.errors import PolicyError
from hugrgate.provenance import DecisionRecord, ProvenanceStore

ALPHA = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}
BETA = {"alpha": 0.2, "beta": 0.6, "gamma": 0.2}


def _ensemble():
    members = [ConstantBackend("a", "alpha", ALPHA),
               ConstantBackend("b", "alpha", ALPHA),
               ConstantBackend("c", "beta", BETA)]
    return Ensemble(members, strategy="weighted",
                    weights={"a": 1.0, "b": 1.0, "c": 1.0})


# --- success -----------------------------------------------------------------

def test_ensemble_decision_recorded_with_council_detail():
    store = ProvenanceStore()
    ens = _ensemble()
    result = ens.evaluate({"x": 1}, CAT_SPEC())
    stored = record_ensemble_decision(store, {"x": 1}, CAT_SPEC(),
                                      result)
    assert isinstance(stored, DecisionRecord)
    assert stored.record_hash  # hash-chained by the store
    assert stored.backend == "ensemble[weighted]"
    block = stored.metadata["ensemble"]
    assert block["recorded"] is True
    assert block["strategy"] == "weighted"
    assert block["members"] == ["a", "b", "c"]
    ballots = {b["backend"]: b["value"] for b in block["member_votes"]}
    assert ballots == {"a": "alpha", "b": "alpha", "c": "beta"}
    assert block["winner_share"] == pytest.approx(2 / 3)
    assert block["weights"] == pytest.approx(
        {"a": 1 / 3, "b": 1 / 3, "c": 1 / 3})
    # minority report travels with the record (slice 114)
    assert [d["backend"] for d in block["minority_report"]] == ["c"]
    # store untouched by later mutation of the returned copy
    assert store.verify_chain() is True
    assert store.count() == 1


def test_membership_events_attached():
    store = ProvenanceStore()
    mgr = MembershipManager([ConstantBackend("a", "alpha", ALPHA),
                             ConstantBackend("c", "beta", BETA)])
    mgr.to_standby("c", reason="maintenance")
    ens = _ensemble()
    result = ens.evaluate({"x": 1}, CAT_SPEC())
    stored = record_ensemble_decision(store, {"x": 1}, CAT_SPEC(),
                                      result,
                                      membership_events=mgr.events())
    events = stored.metadata["ensemble"]["membership_events"]
    assert len(events) == 1
    assert events[0]["kind"] == "standby"
    assert events[0]["member"] == "c"
    assert store.verify_chain() is True


def test_chain_integrity_across_many_records():
    store = ProvenanceStore()
    ens = _ensemble()
    for i in range(5):
        result = ens.evaluate({"i": i}, CAT_SPEC())
        record_ensemble_decision(store, {"i": i}, CAT_SPEC(),
                                 result)
    assert store.count() == 5
    assert store.verify_chain() is True
    hashes = [r.record_hash for r in store.recent(5)]
    assert len(set(hashes)) == 5


def test_find_ensemble_records_filters_strategy():
    store = ProvenanceStore()
    ens_w = _ensemble()
    members = [ConstantBackend("a", "alpha", ALPHA),
               ConstantBackend("b", "beta", BETA)]
    ens_h = Ensemble(members, strategy="hard")
    for ens in (ens_w, ens_h, ens_w):
        result = ens.evaluate({"x": 1}, CAT_SPEC())
        record_ensemble_decision(store, {"x": 1}, CAT_SPEC(),
                                 result)
    assert len(find_ensemble_records(store)) == 3
    weighted = find_ensemble_records(store, strategy="weighted")
    assert len(weighted) == 2
    assert all(r.metadata["ensemble"]["strategy"] == "weighted"
               for r in weighted)
    assert find_ensemble_records(store, strategy="soft") == []


def test_non_ensemble_result_recorded_without_detail():
    store = ProvenanceStore()
    backend = ConstantBackend("solo", "alpha", ALPHA)
    result = backend.evaluate({"x": 1}, CAT_SPEC())
    stored = record_ensemble_decision(store, {"x": 1}, CAT_SPEC(),
                                      result)
    block = stored.metadata["ensemble"]
    assert block["recorded"] is False
    assert find_ensemble_records(store) == []
    assert store.verify_chain() is True


def test_redact_input_still_records_ensemble_detail():
    store = ProvenanceStore()
    ens = _ensemble()
    result = ens.evaluate({"secret": 1}, CAT_SPEC())
    stored = record_ensemble_decision(store, {"secret": 1},
                                      CAT_SPEC(), result,
                                      redact_input=True)
    assert "state_keys" not in stored.metadata
    assert stored.metadata["ensemble"]["strategy"] == "weighted"


def test_abstention_can_be_recorded():
    from hugrgate.abstain import abstain
    store = ProvenanceStore()
    result = abstain(CAT_SPEC(), reason="quiet", backend="ensemble")
    stored = record_ensemble_decision(store, {"x": 1}, CAT_SPEC(),
                                      result)
    assert stored.value is None
    assert stored.accepted is False
    assert store.verify_chain() is True


# --- failure -----------------------------------------------------------------

def test_store_type_checked():
    ens = _ensemble()
    result = ens.evaluate({"x": 1}, CAT_SPEC())
    with pytest.raises(PolicyError, match="ProvenanceStore"):
        record_ensemble_decision(object(), {"x": 1}, CAT_SPEC(),
                                 result)
    with pytest.raises(PolicyError, match="n must be"):
        find_ensemble_records(ProvenanceStore(), n=0)


# --- boundary -----------------------------------------------------------------

def test_find_ignores_records_without_ensemble_block():
    store = ProvenanceStore()
    record = DecisionRecord.from_decision(
        {"x": 1}, CAT_SPEC(),
        ConstantBackend("solo", "alpha", ALPHA).evaluate({"x": 1},
                                                          CAT_SPEC()))
    store.append(record)  # raw record, no ensemble block at all
    assert find_ensemble_records(store) == []
    assert store.verify_chain() is True
