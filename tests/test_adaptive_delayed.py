"""Slice 128 — delayed-label ingestion tests."""

from __future__ import annotations

import time

import pytest

from hugrgate.adaptive.delayed import (
    DelayedLabel,
    DelayedLabelIngestion,
    SweepReport,
)
from hugrgate.adaptive.feedback import OutcomeFeedbackAPI
from hugrgate.adaptive.telemetry import RouteEvent, TelemetryStore
from hugrgate.errors import SpecError


def make_api():
    store = TelemetryStore()
    return OutcomeFeedbackAPI(store)


def record_telemetry(api, rid="r1"):
    api.store.record(RouteEvent(
        request_id=rid, timestamp=time.time(),
        spec={"type": "binary"}, features={"f": 1.0},
        candidates=["a", "b"], propensities={"a": 0.5, "b": 0.5},
        chosen="a", policy_version="v1", privacy_class="standard"))


# --- success ---------------------------------------------------------------

def test_ingest_applies_immediately_when_telemetry_present():
    api = make_api()
    record_telemetry(api)
    ing = DelayedLabelIngestion(api)
    status = ing.ingest(DelayedLabel(request_id="r1", quality=0.8,
                                     label="success"))
    assert status == "applied"
    assert api.store.get("r1").quality == 0.8
    assert len(ing) == 0

def test_ingest_parks_label_when_telemetry_missing():
    api = make_api()
    ing = DelayedLabelIngestion(api)
    status = ing.ingest(DelayedLabel(request_id="r9", quality=0.8))
    assert status == "pending"
    assert ing.pending_ids() == ["r9"]

def test_drain_applies_parked_label_once_telemetry_arrives():
    api = make_api()
    ing = DelayedLabelIngestion(api)
    ing.ingest(DelayedLabel(request_id="r9", quality=0.7, label="partial"))
    record_telemetry(api, "r9")
    assert ing.drain() == 1
    assert api.store.get("r9").quality == 0.7
    assert len(ing) == 0

def test_sweep_expires_stale_labels_and_counts_them():
    api = make_api()
    ing = DelayedLabelIngestion(api, ttl_s=10.0)
    now = time.time()
    ing.ingest(DelayedLabel(request_id="old", quality=0.5,
                            received_at=now - 100.0))
    assert ing.dropped_expired == 1  # expired on arrival
    ing.ingest(DelayedLabel(request_id="fresh", quality=0.5,
                            received_at=now))
    report = ing.sweep(now=now + 50.0)
    assert isinstance(report, SweepReport)
    assert report.expired == 1
    assert report.still_pending == 0
    assert ing.dropped_expired == 2

def test_sweep_applies_matchable_labels():
    api = make_api()
    ing = DelayedLabelIngestion(api, ttl_s=100.0)
    now = time.time()
    ing.ingest(DelayedLabel(request_id="r1", quality=0.6, received_at=now))
    record_telemetry(api, "r1")
    report = ing.sweep(now=now + 5.0)
    assert report.applied == 1
    assert report.still_pending == 0
    assert api.store.get("r1").quality == 0.6

def test_duplicate_parked_label_keeps_earliest_arrival():
    api = make_api()
    ing = DelayedLabelIngestion(api, ttl_s=100.0)
    now = time.time()
    ing.ingest(DelayedLabel(request_id="r1", quality=0.1,
                            received_at=now))
    # A later duplicate does not extend or replace the pending label.
    assert ing.ingest(DelayedLabel(request_id="r1", quality=0.9,
                                   received_at=now + 10.0)) == "pending"
    record_telemetry(api, "r1")
    ing.drain(now=now + 20.0)
    assert api.store.get("r1").quality == 0.1

# --- failure ---------------------------------------------------------------

def test_malformed_label_rejected_before_queueing():
    api = make_api()
    ing = DelayedLabelIngestion(api)
    with pytest.raises(SpecError):
        ing.ingest(DelayedLabel(request_id="r1", quality=99.0))
    assert len(ing) == 0
    with pytest.raises(SpecError):
        ing.ingest(DelayedLabel(request_id="r1", quality=0.5,
                                label="bogus"))
    assert len(ing) == 0

def test_pending_queue_bound_enforced():
    api = make_api()
    ing = DelayedLabelIngestion(api, max_pending=1)
    ing.ingest(DelayedLabel(request_id="a", quality=0.5))
    with pytest.raises(SpecError):
        ing.ingest(DelayedLabel(request_id="b", quality=0.5))

def test_bad_constructor_args_rejected():
    api = make_api()
    with pytest.raises(SpecError):
        DelayedLabelIngestion(api, ttl_s=0)
    with pytest.raises(SpecError):
        DelayedLabelIngestion(api, max_pending=0)

def test_late_duplicate_for_labeled_event_is_dropped():
    api = make_api()
    record_telemetry(api, "r1")
    api.record_outcome("r1", quality=0.9)
    ing = DelayedLabelIngestion(api)
    assert ing.ingest(DelayedLabel(request_id="r1", quality=0.1)) == "expired"
    assert api.store.get("r1").quality == 0.9  # original kept
