"""Slice 126 — routing telemetry dataset tests."""

from __future__ import annotations

import json
import time

import pytest

from hugrgate.adaptive.telemetry import (
    SCHEMA_VERSION,
    RouteEvent,
    TelemetryStore,
)
from hugrgate.errors import SpecError


def make_event(request_id="r1", chosen="a", **over):
    params = dict(
        request_id=request_id,
        timestamp=1234.0,
        spec={"type": "categorical", "options": ["x", "y"]},
        features={"f1": 1.0, "f2": 0.5},
        candidates=["a", "b"],
        propensities={"a": 0.7, "b": 0.3},
        chosen=chosen,
        policy_version="v1",
        privacy_class="standard",
        latency_ms=12.0,
        cost=0.01,
        energy_wh=0.0001,
        immediate_quality=0.8,
    )
    params.update(over)
    return RouteEvent(**params)


# --- success ---------------------------------------------------------------

def test_record_and_get_round_trip(tmp_path):
    store = TelemetryStore(str(tmp_path / "t.jsonl"))
    rid = store.record(make_event())
    assert rid == "r1"
    got = store.get("r1")
    assert got is not None and got.chosen == "a"
    assert got.quality == 0.8  # immediate quality before labeling
    assert not got.labeled

def test_attach_outcome_makes_event_labeled():
    store = TelemetryStore()
    store.record(make_event())
    store.attach_outcome("r1", {"quality": 0.95, "label": "success",
                                "source": "human"})
    got = store.get("r1")
    assert got.labeled and got.quality == 0.95

def test_persistence_reload_merges_outcomes(tmp_path):
    path = str(tmp_path / "t.jsonl")
    store = TelemetryStore(path)
    store.record(make_event())
    store.attach_outcome("r1", {"quality": 0.4})
    reloaded = TelemetryStore(path)
    assert len(reloaded) == 1
    assert reloaded.get("r1").quality == 0.4
    lines = open(path).read().strip().split("\n")
    assert len(lines) == 2  # route_event + outcome (append-only)
    assert {json.loads(l)["kind"] for l in lines} == {"route_event", "outcome"}

def test_export_import_round_trip(tmp_path):
    store = TelemetryStore()
    store.record(make_event("r1"))
    store.record(make_event("r2", chosen="b"))
    store.attach_outcome("r1", {"quality": 1.0})
    out = str(tmp_path / "export.jsonl")
    assert store.export(out) == 2
    imported = TelemetryStore.import_file(out)
    assert len(imported) == 2
    assert imported.get("r1").labeled
    assert not imported.get("r2").labeled

def test_max_records_evicts_oldest():
    store = TelemetryStore(max_records=2)
    for i in range(3):
        store.record(make_event(f"r{i}"))
    assert len(store) == 2
    assert "r0" not in store and "r2" in store

def test_stats_counts():
    store = TelemetryStore()
    store.record(make_event("r1"))
    store.record(make_event("r2", shadow=True))
    store.attach_outcome("r1", {"quality": 0.5})
    stats = store.stats()
    assert stats == {"schema": SCHEMA_VERSION, "n_events": 2, "n_labeled": 1,
                     "n_shadow": 1, "label_rate": 0.5, "max_records": 100000,
                     "path": None}

def test_labeled_unlabeled_iterators():
    store = TelemetryStore()
    store.record(make_event("r1"))
    store.record(make_event("r2"))
    store.attach_outcome("r1", {"quality": 0.5})
    assert [e.request_id for e in store.labeled()] == ["r1"]
    assert [e.request_id for e in store.unlabeled()] == ["r2"]

# --- failure ---------------------------------------------------------------

def test_chosen_must_be_a_candidate():
    with pytest.raises(SpecError):
        make_event(chosen="zzz")

def test_propensities_must_sum_to_one():
    with pytest.raises(SpecError):
        make_event(propensities={"a": 0.5, "b": 0.3})

def test_chosen_propensity_must_be_positive():
    with pytest.raises(SpecError):
        make_event(propensities={"a": 0.0, "b": 1.0}, chosen="a")

def test_duplicate_request_id_rejected():
    store = TelemetryStore()
    store.record(make_event("r1"))
    with pytest.raises(SpecError):
        store.record(make_event("r1"))

def test_attach_outcome_unknown_id_raises_keyerror():
    store = TelemetryStore()
    with pytest.raises(KeyError):
        store.attach_outcome("nope", {"quality": 0.5})

def test_attach_outcome_twice_rejected():
    store = TelemetryStore()
    store.record(make_event("r1"))
    store.attach_outcome("r1", {"quality": 0.5})
    with pytest.raises(SpecError):
        store.attach_outcome("r1", {"quality": 0.9})

def test_bad_outcome_quality_rejected():
    store = TelemetryStore()
    store.record(make_event("r1"))
    with pytest.raises(SpecError):
        store.attach_outcome("r1", {"quality": 1.5})

def test_non_jsonable_spec_rejected():
    with pytest.raises(SpecError):
        make_event(spec={"type": object()})

def test_wrong_schema_rejected_on_load(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps({"schema": "nope", "kind": "route_event"}) + "\n")
    with pytest.raises(SpecError):
        TelemetryStore(str(path))

def test_corrupt_line_rejected(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("{not json\n")
    with pytest.raises(SpecError):
        TelemetryStore(str(path))

def test_max_records_must_be_positive():
    with pytest.raises(SpecError):
        TelemetryStore(max_records=0)

# --- boundary --------------------------------------------------------------

def test_empty_candidates_rejected():
    with pytest.raises(SpecError):
        make_event(candidates=[], propensities={})

def test_quality_bounds_enforced():
    with pytest.raises(SpecError):
        make_event(immediate_quality=-0.1)
    with pytest.raises(SpecError):
        make_event(immediate_quality=1.1)

def test_negative_cost_rejected():
    with pytest.raises(SpecError):
        make_event(cost=-1.0)

def test_get_returns_copy_not_live_reference():
    store = TelemetryStore()
    store.record(make_event("r1"))
    got = store.get("r1")
    got.features["f1"] = 999.0
    assert store.get("r1").features["f1"] == 1.0

def test_new_request_id_unique():
    ids = {TelemetryStore.new_request_id() for _ in range(100)}
    assert len(ids) == 100
