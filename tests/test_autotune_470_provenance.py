"""Slice 470 — optimization provenance. Unit tests."""

from __future__ import annotations

import pytest

from hugrgate.autotune.controller import (
    ConfigStore,
    Disposition,
    Mode,
    OptimizationController,
    Proposal,
    TunableParameter,
    TuningContext,
)
from hugrgate.autotune.provenance import (
    OptimizationProvenance,
    OptimizationRecord,
    ProvenanceTracker,
    hash_mapping,
)
from hugrgate.errors import ReproducibilityError


def _record(**kw):
    base = dict(record_id="r1", timestamp=1.0, tuner="tuner-a",
                proposal_id="p1", mode="offline", disposition="recorded",
                changes={"t": 0.8}, config_before_hash="aa",
                config_after_hash="bb", data_fingerprint="data-1", seed=7)
    base.update(kw)
    return OptimizationRecord(**base)


def test_hash_mapping_stable():
    assert hash_mapping({"b": 2, "a": 1}) == hash_mapping({"a": 1, "b": 2})
    assert hash_mapping({"a": 1}) != hash_mapping({"a": 2})


def test_chain_verifies_and_detects_tamper():
    store = OptimizationProvenance()
    store.append(_record(record_id="r1"))
    store.append(_record(record_id="r2", proposal_id="p2"))
    assert store.verify_chain()
    # tamper with the first record's payload
    store._records[0].changes["t"] = 0.1
    assert not store.verify_chain()
    # reordering also breaks the chain
    store2 = OptimizationProvenance()
    a, b = _record(record_id="r1"), _record(record_id="r2")
    store2.append(a)
    store2.append(b)
    store2._records.reverse()
    assert not store2.verify_chain()


def test_sealed_record_self_verifies():
    store = OptimizationProvenance()
    rec = store.append(_record())
    assert rec.prev_hash == ""
    assert rec.record_hash
    assert rec.verify("")


def test_query_helpers():
    store = OptimizationProvenance()
    store.append(_record(record_id="r1", tuner="ta", proposal_id="p1"))
    store.append(_record(record_id="r2", tuner="tb", proposal_id="p1"))
    store.append(_record(record_id="r3", tuner="ta", proposal_id="p2"))
    assert len(store.by_proposal("p1")) == 2
    assert len(store.by_tuner("ta")) == 2
    assert [r.record_id for r in store.recent(2)] == ["r2", "r3"]
    assert len(store) == 3
    assert len(store.export()) == 3


def test_max_records_bounded():
    store = OptimizationProvenance(max_records=2)
    for i in range(4):
        store.append(_record(record_id=f"r{i}"))
    assert len(store) == 2
    # chain still verifies over the retained suffix... but the first
    # retained record's prev_hash points at an evicted record, so a
    # strict chain check fails: document the tradeoff honestly
    assert not store.verify_chain()


def test_secret_redaction():
    rec = _record(changes={"api_token": "hunter2", "t": 0.5})
    d = rec.to_dict()
    assert d["changes"] == {"api_token": "<redacted>", "t": 0.5}
    # the sealed hash commits to the redacted form
    store = OptimizationProvenance()
    store.append(rec)
    assert store.verify_chain()


def test_tracker_records_controller_run():
    store = ConfigStore()
    store.register(TunableParameter(name="t", dtype="float", default=0.5,
                                    lo=0.0, hi=1.0))
    c = OptimizationController(store=store)
    c.register_objective("o", lambda values: 0.0)

    class _T:
        name = "tuner-a"

        def tune(self, ctx: TuningContext) -> Proposal | None:
            return Proposal(proposal_id="p-1", tuner="tuner-a",
                            changes={"t": 0.8}, objective_id="o",
                            baseline=0.0, estimate=1.0, seed=1)

    c.register_tuner(_T())
    before = store.snapshot()
    run = c.run_cycle(mode=Mode.OFFLINE, seed=7)
    after = store.snapshot()
    tracker = ProvenanceTracker()
    n = tracker.track_run(run, before, after, data_fingerprint="ds-v3",
                          tuner_of={"p-1": "tuner-a"})
    assert n == 1
    rec = tracker.provenance.recent(1)[0]
    assert rec.tuner == "tuner-a" and rec.proposal_id == "p-1"
    assert rec.mode == "offline" and rec.seed == 7
    assert rec.data_fingerprint == "ds-v3"
    assert rec.config_before_hash == hash_mapping(before)
    assert tracker.verify()


def test_tracker_empty_run_records_heartbeat():
    from hugrgate.autotune.controller import TuningRun
    run = TuningRun(run_id="r", mode=Mode.OFFLINE, seed=1,
                    started_at=0.0, finished_at=0.0, results=[])
    tracker = ProvenanceTracker()
    assert tracker.track_run(run, {"a": 1}, {"a": 1}) == 1
    rec = tracker.provenance.recent(1)[0]
    assert rec.disposition == Disposition.SKIPPED.value


def test_verify_raises_on_tamper():
    tracker = ProvenanceTracker()
    tracker.provenance.append(_record())
    tracker.provenance._records[0].seed = 999
    with pytest.raises(ReproducibilityError):
        tracker.verify()
